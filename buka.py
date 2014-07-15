#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Python 3.x

__author__ = "Gumble <abcdoyle888@gmail.com>"
__version__ = "2.1"

'''
布卡漫画转换工具
支持 .buka, .bup.view, .jpg.view

API: import buka
'''

import sys
if sys.version_info[0] < 3:
	print('requires Python 3. try:\n python3 ' + sys.argv[0])
	sys.exit(1)

import os
import shutil
import argparse
import time
import json
import struct
import sqlite3
import logging, logging.config
import traceback
import threadpool
from io import StringIO
from collections import OrderedDict
from subprocess import Popen, PIPE
from platform import machine
from multiprocessing import cpu_count

try:
	# requires Pillow with WebP support
	from PIL import Image
	import PIL.WebPImagePlugin
	SUPPORTPIL = True
except ImportError:
	SUPPORTPIL = False

NT_SLEEP_SEC = 6
logstr = StringIO()

class BadBukaFile(Exception):
	pass

class ArgumentParserWait(argparse.ArgumentParser):
	'''For Windows: makes the cmd window delay.'''
	def exit(self, status=0, message=None):
		if message:
			self._print_message(message, sys.stderr)
		if os.name == 'nt':
			time.sleep(NT_SLEEP_SEC)
		sys.exit(status)

class tTree():
	'''The Tree format:
	   tTree[('foo', 'bar', 'baz')] = 42
	   which auto creates:
	   tTree[('foo', 'bar')] = None
	   tTree[('foo', )] = None
	'''
	def __init__(self):
		self.d = {}
	
	def __len__(self):
		return len(self.d)
	
	def __getitem__(self, key):
		return self.d[tuple(key)]
	
	def __setitem__(self, key, value):
		key = tuple(key)
		if key not in self.d:
			for i in range(1, len(key)):
				if key[:i] not in self.d:
					self.d[key[:i]] = None
		self.d[key] = value
	
	def __delitem__(self, key):
		del self.d[tuple(key)]

	def __iter__(self):
		return iter(self.d)
	
	def __contains__(self, item):
		return tuple(item) in self.d
	
	def keys(self):
		return self.d.keys()
	
	def get(self, key, default=None):
		key = tuple(key)
		if key in self.d:
			return self.d[key]
		else:
			return default
	
	def __repr__(self):
		return repr(self.d)

class BukaFile:
	'''Reads the buka file.'''
	def __init__(self, filename):
		self.filename = filename
		f = self.fp = open(filename, 'rb')
		buff = f.read(128)
		if buff[0:4] != b'buka':
			raise BadBukaFile('not a buka file')
		self.comicid = struct.unpack('<I', buff[12:16])[0]
		self.chapid = struct.unpack('<I', buff[16:20])[0]
		pos = buff.find(b'\x00', 20)
		self.comicname = buff[20:pos].decode(encoding='utf-8', errors='ignore')
		pos += 1
		endhead = pos + struct.unpack('<I', buff[pos:pos + 4])[0] - 1
		pos += 4
		f.seek(pos)
		buff = f.read(endhead-pos+1)
		self.files = OrderedDict() # {}
		pos = 0
		while pos + 8 < len(buff):
			pointer, size = struct.unpack('<II', buff[pos:pos + 8])
			pos += 8
			end = buff.find(b'\x00', pos)
			name = buff[pos:end].decode(encoding='utf-8', errors='ignore')
			pos = end + 1
			self.files[name] = (pointer, size)
		try:
			self.fp.seek(self.files['chaporder.dat'][0])
			self._chaporderdat = self.fp.read(self.files['chaporder.dat'][1])
			self.chapinfo = ComicInfo(json.loads(self._chaporderdat.decode('utf-8')))
			if self.chapinfo.comicid is None:
				chapinfo.comicid = self.comicid
		except KeyError:
			self._chaporderdat, self.chapinfo = None, None
			
	
	def __len__(self):
		return len(self.files)
	
	def __getitem__(self, key):
		if key in self.files:
			if key == 'chaporder.dat' and self._chaporderdat:
				return self._chaporderdat
			index = self.files[key]
			self.fp.seek(index[0])
			return self.fp.read(index[1])
		else:
			raise KeyError(key)
	
	def __iter__(self):
		return iter(self.files)
	
	def __contains__(self, item):
		return item in self.files
	
	def keys(self):
		return self.files.keys()
	
	def getfile(self, key, offset=0):
		'''offset is for bup files.'''
		if key == 'chaporder.dat' and self._chaporderdat:
			return self._chaporderdat
		index = self.files[key]
		self.fp.seek(index[0] + offset)
		return self.fp.read(index[1] - offset)
	
	def extract(self, key, path):
		with open(path, 'wb') as w:
			index = self.files[key]
			self.fp.seek(index[0])
			w.write(self.fp.read(index[1]))
	
	def extractall(self, path):
		if not os.path.exists(path):
			os.makedirs(path)
		for key in self.files:
			self.extract(key, os.path.join(path, key))
	
	def __repr__(self):
		return "<BukaFile comicid=%r chapid=%r comicname=%r>" % \
			(self.comicid, self.chapid, self.comicname)
	
	def close(self):
		self.fp.close()
	
	def __del__(self):
		self.fp.close()

class ComicInfo:
	'''This class represents the items in chaporder.dat,
	   and provides convenient access to chapters.
	'''
	def __init__(self, chaporder, comicid=None):
		self.chaporder = chaporder
		self.comicname = chaporder['name']
		self.chap = {}
		for d in chaporder['links']:
			self.chap[int(d['cid'])] = d
		if comicid:
			self.comicid = comicid
		else:
			try:
				self.comicid = int(chaporder['logo'].split('/')[-1].split('-')[0])
			except ValueError:
				logging.debug("can't get comicid from url: %s", chaporder['logo'])
				self.comicid = None
	
	def renamef(self, cid):
		if cid in self.chap:
			if self.chap[cid]['title']:
				return self.chap[cid]['title']
			else:
				if self.chap[cid]['type'] == '0':
					return '第' + self.chap[cid]['idx'].zfill(2) + '卷'
				elif self.chap[cid]['type'] == '1':
					return '第' + self.chap[cid]['idx'].zfill(3) + '话'
				elif self.chap[cid]['type'] == '2':
					return '番外' + self.chap[cid]['idx'].zfill(2)
				else:
					return self.chap[cid]['idx'].zfill(3)
		else:
			return str(cid)
	
	def __getitem__(self, key):
		if key in self.chaporder:
			return self.chaporder[key]
		else:
			raise KeyError(key)
	
	def __contains__(self, item):
		return item in self.chaporder

	def __repr__(self):
		return "<ComicInfo comicid=%r comicname=%r>" % (self.comicid, self.comicname)

class DirMan:
	'''This class mainly maintains three items:
	   self.nodes - represents the directory tree and what it contains.
	   self.comicdict - maintains the dictionary of known comic entries.
	   self.dwebpman - puts decode requests
	'''
	def __init__(self, dirpath, dwebpman, comicdict={}):
		self.dirpath = dirpath
		self.nodes = tTree()
		self.dwebpman = dwebpman
		self.comicdict = comicdict
	
	def __repr__(self):
		return "<DirMan dirpath=%r>" % self.dirpath
	
	def cutname(self, filename):
		'''cut the filename to be relative to the base directory name.
		   avoid renaming outer directories.
		'''
		return os.path.relpath(filename, os.path.dirname(self.dirpath))
	
	def updatecomicdict(self, comicinfo):
		if comicinfo.comicid in self.comicdict:
			self.comicdict[comicinfo.comicid].chaporder.update(comicinfo.chaporder)
			self.comicdict[comicinfo.comicid].chap.update(comicinfo.chap)
		else:
			self.comicdict[comicinfo.comicid] = comicinfo
	
	def detectndecode(self):
		'''detect what the directory contains, attach it to its contents,
		   and decode bup/webp images.
		'''
		ifndef = lambda x,y: x if x else y
		removefiles = []
		for root, subFolders, files in os.walk(self.dirpath):
			dtype = None
			#frombup = set()
			if 'chaporder.dat' in files:
				filename = os.path.join(root, 'chaporder.dat')
				chaporder = ComicInfo(json.load(open(filename, 'r')))
				try:
					tempid = int(os.path.basename(root))
					if tempid == chaporder.comicid:
						dtype = ifndef(dtype, ('comic', chaporder.comicname))
					elif tempid in chaporder.chap:
						dtype = ifndef(dtype, ('chap', chaporder.comicname, chaporder.renamef(tempid)))
					elif chaporder.comicid is None:
						dtype = ifndef(dtype, ('comic', chaporder.comicname))
						chaporder.comicid = tempid
					#else:
						#dtype = None
						#pass
				except ValueError:
					#dtype = None
					pass
				self.updatecomicdict(chaporder)
			for name in files:
				filename = os.path.join(root, name)
				if detectfile(filename) == 'buka' and not subFolders and (name == 'pack.dat' or len(files)<3): # only a buka (and a chaporder)
					logging.info('正在提取 ' + self.cutname(filename))
					buka = BukaFile(filename)
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						dtype = ifndef(dtype, ('chap', buka.comicname, chaporder.renamef(int(os.path.basename(root)))))
					elif buka.comicid in self.comicdict:
						dtype = ifndef(dtype, ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid)))
					extractndecode(buka, root, self.dwebpman)
					buka.close()
					removefiles.append(filename)
				elif detectfile(filename) == 'buka':
					logging.info('正在提取 ' + self.cutname(filename))
					buka = BukaFile(filename)
					sp = splitpath(self.cutname(os.path.join(root, os.path.splitext(name)[0])))
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						self.nodes[sp] = ('chap', buka.comicname, chaporder.renamef(buka.chapid))
					elif buka.comicid in self.comicdict:
						self.nodes[sp] = ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid))
					extractndecode(buka, os.path.join(root, os.path.splitext(name)[0]), self.dwebpman)
					try:
						tempid = int(os.path.basename(root))
						if tempid == buka.comicid:
							dtype = ifndef(dtype, ('comic', buka.comicname))
					except ValueError:
						pass
					buka.close()
					removefiles.append(filename)
				elif detectfile(filename) == 'bup':
					logging.info('加入队列 ' + self.cutname(filename))
					with open(filename, 'rb') as f, open(os.path.splitext(filename)[0] + '.webp', 'wb') as w:
						f.seek(64)
						shutil.copyfileobj(f, w)
					#frombup.add(os.path.splitext(filename)[0] + '.webp')
					self.dwebpman.add(os.path.splitext(filename)[0], self.cutname(filename))
					removefiles.append(filename)
					#decodewebp(os.path.splitext(filename)[0])
				# No way! don't let webp's confuse the program.
				#elif detectfile(filename) == 'webp':
					#if os.path.isfile(os.path.splitext(filename)[0]+'.bup') or filename in frombup:
						#continue
					#logging.info('加入队列 ' + self.cutname(filename))
					#self.dwebpman.add(os.path.splitext(filename)[0], self.cutname(filename))
					##decodewebp(os.path.splitext(filename)[0])
				elif name == 'buka_store.sql':
					try:
						cdict = buildfromdb(filename)
						for key in cdict:
							self.updatecomicdict(cdict[key])
					except:
						logging.error('不是有效的数据库: ' + self.cutname(filename))
				#else:
					#dtype = 'unk'
			#for name in subFolders:
				#pass
			sp = splitpath(self.cutname(root))
			if not dtype:
				try:
					tempid = int(os.path.basename(root))
					if tempid in self.comicdict:
						dtype = ('comic', self.comicdict[tempid].comicname)
					else:
						try:
							tempid2 = int(os.path.basename(os.path.dirname(root)))
							if tempid2 in self.comicdict:
								if tempid in self.comicdict[tempid2].chap:
									dtype = ('chap', self.comicdict[tempid2].comicname, self.comicdict[tempid2].renamef(tempid))
						except ValueError:
							pass
				except ValueError:
					pass
			self.nodes[sp] = dtype
		# just for the low speed of Windows
		for filename in removefiles:
			tryremove(filename)
	
	def renamedirs(self):
		'''do the renaming.'''
		ls = sorted(self.nodes.keys(), key=len, reverse=True)
		for i in ls:
			this = self.nodes.get(i)
			parent = self.nodes.get(i[:-1])
			if this:
				origpath = os.path.join(os.path.dirname(self.dirpath), *i)
				basepath = os.path.join(os.path.dirname(self.dirpath), *i[:-1])
				if this[0] == 'comic':
					movedir(origpath, os.path.join(basepath, this[1]))
				elif parent:
					if this[1] == parent[1]:
						movedir(origpath, os.path.join(basepath, this[2]))
				else:
					movedir(origpath, os.path.join(basepath, this[1] + '-' + this[2]))
	
def movedir(src, dst):
	if src == dst:
		pass
	elif os.path.isdir(src) and os.path.isdir(dst):
		for item in os.listdir(src):
			movedir(os.path.join(src, item), os.path.join(dst, item))
		os.rmdir(src)
	else:
		shutil.move(src, dst)

def tryremove(filename):
	# just for the low speed of Windows
	for att in range(5):
		try:
			os.remove(filename)
			break
		except PermissionError as ex:
			logging.debug("Delete failed, trying...")
			if att == 4:
				raise ex
			time.sleep(0.25)

def splitpath(path):
	folders = []
	path = path.rstrip(r'\\').rstrip(r'/')
	while 1:
		path,folder = os.path.split(path)
		if folder != "":
			folders.append(folder)
		else:
			if path != "":
				folders.append(path)
			break
	folders.reverse()
	return folders

def extractndecode(bukafile, path, dwebpman):
	'''for extracting buka files'''
	if not os.path.exists(path):
		os.makedirs(path)
	for key in bukafile.files:
		if os.path.splitext(key)[1] == '.bup':
			with open(os.path.join(path, os.path.splitext(key)[0] + '.webp'), 'wb') as f:
				f.write(bukafile.getfile(key,64))
			# decodewebp(os.path.join(path, os.path.splitext(key)[0]))
			dwebpman.add(os.path.join(path, os.path.splitext(key)[0]), os.path.join(os.path.basename(path), key))
		elif key == 'logo':
			with open(os.path.join(path, key + '.jpg'), 'wb') as f:
				f.write(bukafile[key])
		else:
			with open(os.path.join(path, key), 'wb') as f:
				f.write(bukafile[key])

def buildfromdb(dbname):
	'''Build a dict of BukaFile objects from buka_store.sql file in
	   iOS devices.
	   use json.dump(<dictname>[id].chaporder) to generate chaporder.dat from db.
	   '''
	db = sqlite3.connect(dbname)
	c = db.cursor()
	initd = {'author': '', #mangainfo/author
			 'discount': '0', 'favor': 0,
			 'finish': '0', #ismangaend/isend
			 'intro': '',
			 'lastup': '', #mangainfo/recentupdatename
			 'lastupcid': '', #Trim and lookup chapterinfo/fulltitle
			 'lastuptime': '', #mangainfo/recentupdatetime
			 'lastuptimeex': '', #mangainfo/recentupdatetime + ' 00:00:00'
			 'links': [], #From chapterinfo
			 'logo': '', #mangainfo/logopath
			 'logos': '', #mangainfo/logopath.split('-')[0]+'-s.jpg'
			 'name': '', #mangainfo/title
			 'popular': 9999999, 'populars': '10000000+', 'rate': '20',
			 'readmode': 50331648, 'readmode2': '0',
			 'recomctrlparam': '101696', 'recomctrltype': '1',
			 'recomdelay': '2000', 'recomenter': '', 'recomwords': '',
			 'res': [],
			 #'res': [{'cid': '0', #downloadview/cid
				#'csize': '4942', 'restype': '1'}]
			 'resupno': '0', 'ret': 0, 'upno': '0'}
	d = {}
	c.execute('select * from mangainfo')
	while 1:
		lst = c.fetchone()
		if not lst:
			break
		d[lst[0]] = initd.copy()
		d[lst[0]]['name'] = lst[1]
		d[lst[0]]['logo'] = lst[2]
		d[lst[0]]['logos'] = lst[2].split('-')[0] + '-s.jpg'
		d[lst[0]]['lastup'] = lst[3]
		d[lst[0]]['lastuptime'] = lst[4]
		d[lst[0]]['lastuptimeex'] = lst[4] + ' 00:00:00'
		d[lst[0]]['author'] = lst[5]
	c.execute('select * from ismangaend')
	while 1:
		lst = c.fetchone()
		if not lst:
			break
		d[lst[0]]['finish'] = str(lst[1])
	c.execute('select * from chapterinfo')
	while 1:
		lst = c.fetchone()
		if not lst:
			break
		if not d[lst[0]]['links']:
			d[lst[0]]['links'] = []
		if not d[lst[0]]['res']:
			d[lst[0]]['res'] = []
		if lst[3]:
			comictitle = ''
			if lst[3][-1] == '卷':
				comictype = '0'
			elif lst[3][-1] == '话':
				comictype = '1'
			else:
				comictype = '2'
				comictitle = lst[3]
		else:
			comictype = '2'
			comictitle = lst[2]
		d[lst[0]]['links'].append({'cid': str(lst[1]), #chapterinfo/cid
						'idx': str(lst[4]), #chapterinfo/idx
						'ressupport': '7', 'size': '0',
						'title': comictitle, 'type': comictype})
		d[lst[0]]['res'].append({'cid': str(lst[1]), 'csize': '1', 'restype': '1'})
		if not d[lst[0]]['lastupcid']:
			if d[lst[0]]['lastup'].strip() in lst[3]:
				d[lst[0]]['lastupcid'] = str(lst[1])
			elif d[lst[0]]['lastup'].strip() in lst[2]:
				d[lst[0]]['lastupcid'] = str(lst[1])
	db.close()
	return dict(map(lambda k: (k, ComicInfo(d[k], k)), d))

def detectfile(filename):
	"""Tests file format."""
	if not os.path.exists(filename):
		return None
	if os.path.isdir(filename):
		return 'dir'
	if os.path.basename(filename) == 'index2.dat':
		return 'index2'
	elif os.path.basename(filename) == 'chaporder.dat':
		return 'chaporder'
	ext = os.path.splitext(filename)[1]
	if ext == '.buka':
		return 'buka'
	elif ext == '.bup':
		return 'bup'
	elif ext == '.view':
		ext2 = os.path.splitext(os.path.splitext(filename)[0])[1]
		if ext2 == '.jpg':
			return 'jpg'
		elif ext2 == '.bup':
			return 'bup'
		elif ext2 == '.png':
			return 'png'
	with open(filename, 'rb') as f:
		h = f.read(32)
	if h[6:10] in (b'JFIF', b'Exif'):
		return 'jpg'
	elif h.startswith(b'\211PNG\r\n\032\n'):
		return 'png'
	elif h[:4] == b"buka":
		return 'buka'
	elif h[:4] == b"AKUB" or h[12:16] == b"AKUB":
		return 'index2'
	elif h[:4] == b"bup\x00":
		return 'bup'
	elif h.startswith(b'SQLite format 3'):
		return 'sqlite3'
	elif h[:4] == b"RIFF" and h[8:16] == b"WEBPVP8 ":
		return 'webp'
	else:
		return False

def copytree(src, dst, symlinks=False, ignore=None):
	if not os.path.exists(dst):
		os.makedirs(dst)
	for item in os.listdir(src):
		s = os.path.join(src, item)
		d = os.path.join(dst, item)
		if os.path.isdir(s):
			copytree(s, d, symlinks, ignore)
		elif detectfile(s) in ('index2','chaporder','buka','bup','jpg','png','sqlite3','webp'): # whitelist
			if os.path.splitext(s)[1] == '.view':
				d = os.path.splitext(d)[0]
			if not os.path.isfile(d) or os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
				shutil.copy2(s, d)
	if not os.listdir(dst):
		os.rmdir(dst)

class DwebpMan:
	def __init__(self, dwebppath, process):
		programdir = os.path.dirname(os.path.abspath(sys.argv[0]))
		self.fail = False
		if '64' in machine():
			bit = '64'
		else:
			bit = '32'
		logging.debug('os.machine() = %s', machine())
		if dwebppath:
			self.dwebp = dwebppath
		elif os.name == 'nt':
			self.dwebp = os.path.join(programdir, 'dwebp_' + bit + '.exe')
		else:
			self.dwebp = os.path.join(programdir, 'dwebp_' + bit)
		
		nul = open(os.devnull, 'w')
		try:
			p = Popen(self.dwebp, stdout=nul, stderr=nul).wait()
			self.supportwebp = True
		except Exception as ex:
			if os.name == 'posix':
				try:
					p = Popen('dwebp', stdout=nul, stderr=nul).wait()
					self.supportwebp = True
					self.dwebp = 'dwebp'
					logging.info("used dwebp installed in the system.")
				except Exception as ex:
					logging.error("dwebp 不可用，仅支持普通文件格式。")
					logging.debug("dwebp test: " + repr(ex))
					self.supportwebp = False
			else:
				logging.error("dwebp 不可用，仅支持普通文件格式。")
				logging.debug("dwebp test: " + repr(ex))
				self.supportwebp = False
		nul.close()
		logging.debug("dwebp = " + self.dwebp)
		if self.supportwebp:
			self.pool = threadpool.NoOrderedRequestManager(process,self.decodewebp,self.checklog,self.handle_thread_exception)
		else:
			self.pool = None
	
	def __repr__(self):
		return "<DwebpMan supportwebp=%r dwebp=%r>" % (self.supportwebp, self.dwebp)

	def add(self, basepath, displayname):
		if self.pool:
			self.pool.putRequest([basepath, displayname])

	def wait(self):
		self.pool.wait()

	def checklog(self, request, result):
		if 'cannot' in result[1]:
			logging.error("dwebp 错误[%d]: %s", result[0], result[1])
		else:
			logging.info("完成转换 %s", request.args[1])
			logging.debug("dwebp OK[%d]: %s", result[0], result[1])

	def handle_thread_exception(self, request, exc_info):
		"""Logging exception handler callback function."""
		self.fail = True
		logging.getLogger().error(str(request))
		traceback.print_exception(*exc_info, file=logstr)

	def decodewebp(self, basepath, displayname):
		proc = Popen([self.dwebp, basepath + ".webp", "-o", basepath + ".png"], stdout=PIPE, stderr=PIPE, cwd=os.getcwd())
		stdout, stderr = proc.communicate()
		#if stdout:
			#stdout = stdout.decode(errors='ignore')
			#logging.info("dwebp: " + stdout)
		if stderr:
			stderr = stderr.decode(errors='ignore')
		tryremove(basepath + ".webp")
		return (proc.returncode, stderr)

class DwebpPILMan:
	"""
	Use threads of PIL.Image instead of dwebp to decode webps.
	
	Note: For now, this class is available for decoding, and the it's faster.
	      BUT, use this for decoding hundreds of images will cause CPython
	      memory leaks. gc / del / close() don't work. Using multiprocessing
	      is a waste though.
	      So, don't use it for a large number of images.
	      If you can fix it, contact the __author__.
	"""
	def __init__(self, process):
		self.supportwebp = True
		self.fail = False
		self.pool = threadpool.NoOrderedRequestManager(process,self.decodewebp,self.checklog,self.handle_thread_exception)

	def add(self, basepath, displayname):
		self.pool.putRequest([basepath, displayname])

	def wait(self):
		self.pool.wait()

	def checklog(self, request, result):
		if result:
			logging.info("完成转换 %s", request.args[1])
		else:
			logging.error("解码错误: %s", request.args[1])

	def handle_thread_exception(self, request, exc_info):
		"""Logging exception handler callback function."""
		self.fail = True
		logging.getLogger().error(str(request))
		traceback.print_exception(*exc_info, file=logstr)
	
	def decodewebp(self, basepath, displayname):
		im = Image.open(basepath + ".webp")
		im.save(basepath + '.jpg', quality=90)
		im.close()
		del im
		tryremove(basepath + ".webp")
		return True

def logexit(err=True):
	logging.shutdown()
	if err:
		try:
			with open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),'bukaex.log'), 'a') as f:
				f.write(logstr.getvalue())
		except:
			with open('bukaex.log', 'a') as f:
				f.write(logstr.getvalue())
		print('如果不是使用方法错误，请发送错误报告 bukaex.log 给作者 ' + __author__)
	if os.name == 'nt':
		time.sleep(NT_SLEEP_SEC)
	sys.exit(int(err))

def main():
	LOG_CONFIG = {'version':1,
			'formatters':{'strlog':{'format':'*** %(levelname)s	%(funcName)s\n%(message)s'},
						'stderr':{'format':'%(levelname)-7s %(message)s'}},
			'handlers':{'console':{'class':'logging.StreamHandler',
									'formatter':'stderr',
									'level':'INFO',
									'stream':sys.stderr},
						'strlogger':{'class':'logging.StreamHandler',
								  'formatter':'strlog',
								  'level':'DEBUG',
								  'stream':logstr}},
			'root':{'handlers':('console', 'strlogger'), 'level':'DEBUG'}}
	logging.config.dictConfig(LOG_CONFIG)
	try:
		cpus = cpu_count() if cpu_count() else 2
	except NotImplementedError:
		cpus = 1

	parser = ArgumentParserWait(description="Converts comics downloaded by Buka.")
	parser.add_argument("-p", "--process", help="The max number of running dwebp's. (Default = CPU count)", default=cpus, type=int, metavar='NUM')
	parser.add_argument("-s", "--same-dir", action='store_true', help="Change the default output dir to <input>/../output. Ignored when specifies <output>")
	parser.add_argument("-l", "--log", action='store_true', help="Force logging to file.")
	parser.add_argument("--pil", action='store_true', help="Perfer PIL/Pillow for decoding, faster, and may cause memory leaks.")
	# parser.add_argument("--dwebp", nargs='?', help="Perfer dwebp for decoding, and/or locate your own dwebp WebP decoder.", default=None, const=True)
	parser.add_argument("--dwebp", help="Locate your own dwebp WebP decoder.", default=None)
	parser.add_argument("-d", "--db", help="Locate the 'buka_store.sql' file in iOS devices, which provides infomation for renaming.", default=None, metavar='buka_store.sql')
	parser.add_argument("input", help="The .buka file or the folder containing files downloaded by Buka, which is usually located in (Android) /sdcard/ibuka/down")
	parser.add_argument("output", nargs='?', help="The output folder. (Default = ./output)", default=None)
	args = parser.parse_args()
	logging.debug(repr(args))

	programdir = os.path.dirname(os.path.abspath(sys.argv[0]))
	fn_buka = args.input
	if args.output:
		target = args.output
	elif args.same_dir:
		target = os.path.join(os.path.dirname(fn_buka),'output')
	else:
		target = 'output'
	target = os.path.abspath(target)
	logging.debug('target = ' + target)
	if not os.path.exists(target):
		os.makedirs(target)
	dbdict = {}
	if args.db:
		try:
			dbdict = buildfromdb(args.db)
		except:
			logging.error('指定的数据库文件不是有效的 iOS 设备中的 buka_store.sql 数据库文件。提取过程将继续。')
	
	logging.info('%s version %s' % (os.path.basename(sys.argv[0]), __version__))
	logging.info("检查环境...")
	# if args.dwebp == True:
		# dwebpman = DwebpMan(None, args.process)
	if args.dwebp:
		dwebpman = DwebpMan(args.dwebp, args.process)
	elif SUPPORTPIL and args.pil:
		dwebpman = DwebpPILMan(args.process)
	else:
		dwebpman = DwebpMan(args.dwebp, args.process)
	logging.debug("dwebpman = " + repr(dwebpman))

	if os.path.isdir(target):
		if detectfile(fn_buka) == "buka":
			if not os.path.isfile(fn_buka):
				logging.critical('没有此文件: ' + fn_buka)
				if not os.listdir(target):
					os.rmdir(target)
				logexit()
			logging.info('正在提取 ' + fn_buka)
			buka = BukaFile(fn_buka)
			extractndecode(buka, target, dwebpman)
			if dwebpman.supportwebp:
				dwebpman.wait()
			if buka.chapinfo:
				movedir(target, os.path.join(os.path.dirname(target), buka.comicname + '-' + buka.chapinfo.renamef(buka.chapid)))
			else:
				# cannot get chapter name
				movedir(target, os.path.join(os.path.dirname(target), buka.comicname + '-' + buka.chapid))
			buka.close()
		elif os.path.isdir(fn_buka):
			logging.info('正在复制...')
			copytree(fn_buka, target)
			dm = DirMan(target, dwebpman, dbdict)
			dm.detectndecode()
			if dwebpman.supportwebp:
				logging.info("等待所有转换进程/线程...")
				dwebpman.wait()
			logging.info("完成转换。")
			logging.info("正在重命名...")
			dm.renamedirs()
		else:
			logging.critical("输入必须为 buka 文件或一个文件夹。请使用 import buka 来获取 API 接口。")
			if not os.listdir(target):
				os.rmdir(target)
			logexit()
		if dwebpman.fail:
			logexit()
		logging.info('完成。')
		if not dwebpman.supportwebp:
			logging.warning('警告: .bup 格式文件无法提取。')
			logexit()
		if args.log:
			logexit()
	else:
		logging.critical("错误: 输出文件夹路径为一个文件。")
		logexit()

if __name__ == '__main__':
	try:
		main()
	except SystemExit:
		pass
	except:
		logging.exception('错误: 主线程异常退出。')
		logexit()
