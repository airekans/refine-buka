#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Python 3.x

__author__ = "Gumble <abcdoyle888@gmail.com>"
__version__ = "2.4"

'''
Extract images downloaded by Buka.

Supports .buka, .bup.view, .jpg.view formats.
To use:   buka.py input [output]
For help: buka.py -h
API:      import buka
Main features:
  * BukaFile    Reads the buka file.
  * ComicInfo   Get comic information from chaporder.dat.
  * DirMan      Manages directories for converting and renaming.
  * buildfromdb Build a dict of BukaFile objects from buka_store.sql
'''

import sys
if sys.version_info[0] < 3:
	print('requires Python 3. try:\n python3 ' + sys.argv[0])
	sys.exit(1)

import os
import platform
import shutil
import argparse
import time
import json
import struct
import sqlite3
import logging, logging.config
import traceback
import threadpool
from io import StringIO, BytesIO
from collections import OrderedDict, deque
from subprocess import Popen, PIPE
from multiprocessing import cpu_count

try:
	# requires Pillow with WebP support
	from PIL import Image
	import PIL.WebPImagePlugin
	SUPPORTPIL = True
except ImportError:
	SUPPORTPIL = False

NT_SLEEP_SEC = 7
logstr = StringIO()

class BadBukaFile(Exception):
	pass

class ArgumentParserWait(argparse.ArgumentParser):
	'''For Windows: makes the cmd window delay.'''
	def exit(self, status=0, message=None):
		if message:
			self._print_message(message, sys.stderr)
		if os.name == 'nt':
			sys.stderr.write("使用方法不正确。请将文件夹拖至软件图标使用。")
			sys.stderr.flush()
			time.sleep(NT_SLEEP_SEC)
		sys.exit(status)

class tTree():
	'''
	The tTree format for directories.

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
		# I guess it's the version number.
		# [4:8] is more likely a (minor) version
		# [9:12] may be a major version or "file type"
		self.version = struct.unpack('<II', buff[4:12])
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
		if 'chaporder.dat' in self.files:
			self.fp.seek(self.files['chaporder.dat'][0])
			self._chaporderdat = self.fp.read(self.files['chaporder.dat'][1])
			self.chapinfo = ComicInfo(json.loads(self._chaporderdat.decode('utf-8')), self.comicid)
		else:
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
		return "<BukaFile comicid=%r comicname=%r chapid=%r>" % \
			(self.comicid, self.comicname, self.chapid)

	def __str__(self):
		return "漫画: %s, %s" % (self.comicname, self.chapid)

	def close(self):
		self.fp.close()

	def __del__(self):
		self.fp.close()

class ComicInfo:
	'''
	Get comic information from chaporder.dat.

	This class represents the items in chaporder.dat,
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
			self.comicid = chaporder['logo'].split('/')[-1].split('-')[0]
			if self.comicid.isdigit():
				self.comicid = int(self.comicid)
			else:
				logging.debug("can't get comicid from url: %s", chaporder['logo'])
				self.comicid = None

	@staticmethod
	def fromfile(filename):
		return ComicInfo(json.load(open(filename)))

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
		return self.chaporder[key]

	def __contains__(self, item):
		return item in self.chaporder

	def __repr__(self):
		return "<ComicInfo comicid=%r comicname=%r>" % (self.comicid, self.comicname)

	def __str__(self):
		return "漫画: %s" % (self.comicname)


class DirMan:
	'''
	Manages directories for converting and renaming.

	This class mainly maintains three items:
	* self.nodes - represents the directory tree and what it contains.
	* self.comicdict - maintains the dictionary of known comic entries.
	* self.dwebpman - puts decode requests
	'''
	def __init__(self, dirpath, dwebpman=None, origpath=None, comicdict={}):
		self.dirpath = dirpath.rstrip('\\/')
		self.origpath = (origpath or dirpath).rstrip('\\/')
		self.nodes = tTree()
		self.dwebpman = dwebpman
		self.comicdict = comicdict

	def __repr__(self):
		return "<DirMan dirpath=%r origpath=%r>" % (self.dirpath, self.origpath)

	def cutname(self, filename):
		'''
		Cuts the filename to be relative to the base directory name
		to avoid renaming outer directories.
		'''
		return os.path.relpath(filename, os.path.dirname(self.dirpath))

	def basename(self, filename):
		'''
		Cuts the filename to be relative to the base directory name
		to avoid renaming outer directories.
		'''
		if filename == self.dirpath:
			return os.path.basename(self.origpath)
		else:
			return os.path.basename(filename)

	def updatecomicdict(self, comicinfo):
		if comicinfo.comicid in self.comicdict:
			self.comicdict[comicinfo.comicid].chaporder.update(comicinfo.chaporder)
			self.comicdict[comicinfo.comicid].chap.update(comicinfo.chap)
		else:
			self.comicdict[comicinfo.comicid] = comicinfo

	def detect(self):
		'''
		Only detects directory contents.
		'''
		for root, subFolders, files in os.walk(self.dirpath):
			dtype = None
			if 'chaporder.dat' in files:
				filename = os.path.join(root, 'chaporder.dat')
				chaporder = ComicInfo(json.load(open(filename, 'r')))
				tempid = self.basename(root)
				if tempid.isdigit():
					tempid = int(tempid)
					if tempid == chaporder.comicid:
						dtype = dtype or ('comic', chaporder.comicname)
					elif tempid in chaporder.chap:
						dtype = dtype or ('chap', chaporder.comicname, chaporder.renamef(tempid))
					elif chaporder.comicid is None:
						dtype = dtype or ('comic', chaporder.comicname)
						chaporder.comicid = tempid
				self.updatecomicdict(chaporder)
			for name in files:
				filename = os.path.join(root, name)
				if detectfile(filename) == 'buka' and not subFolders and (name == 'pack.dat' or len(files)<4):
					# only a buka (and a chaporder) (and an index2)
					buka = BukaFile(filename)
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						tempid = self.basename(root)
						if tempid.isdigit():
							tempid = int(tempid)
							dtype = dtype or ('chap', buka.comicname, chaporder.renamef(tempid))
					elif buka.comicid in self.comicdict:
						dtype = dtype or ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid))
				elif detectfile(filename) == 'buka':
					buka = BukaFile(filename)
					sp = splitpath(self.cutname(os.path.join(root, os.path.splitext(name)[0])))
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						self.nodes[sp] = ('chap', buka.comicname, chaporder.renamef(buka.chapid))
					elif buka.comicid in self.comicdict:
						self.nodes[sp] = ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid))
					tempid = self.basename(root)
					if tempid.isdigit():
						tempid = int(tempid)
						if tempid == buka.comicid:
							dtype = dtype or ('comic', buka.comicname)
				elif detectfile(filename) == 'bup':
					pass
				elif detectfile(filename) == 'tmp':
					pass
				elif name == 'buka_store.sql':
					try:
						cdict = buildfromdb(filename)
						for key in cdict:
							self.updatecomicdict(cdict[key])
					except Exception:
						pass
			if root == self.dirpath:
				rootdir = self.origpath
			else:
				rootdir = root
			sp = splitpath(self.cutname(root))
			if not dtype:
				tempid = self.basename(rootdir)
				if tempid.isdigit():
					tempid = int(tempid)
					if tempid in self.comicdict:
						dtype = ('comic', self.comicdict[tempid].comicname)
					else:
						tempid2 = self.basename(os.path.dirname(root))
						if tempid2.isdigit():
							tempid2 = int(tempid2)
							if tempid2 in self.comicdict:
								if tempid in self.comicdict[tempid2].chap:
									dtype = ('chap', self.comicdict[tempid2].comicname, self.comicdict[tempid2].renamef(tempid))
			self.nodes[sp] = dtype
		return self.nodes

	def detectndecode(self):
		'''
		Detects what the directory contains, attach it to its contents,
		and decode bup/webp images.
		'''
		# ifndef = lambda x,y: x if x else y
		#        ==> x or y
		if self.dwebpman is None:
			raise NotImplementedError('dwebpman must be specified first.')
		removefiles = []
		for root, subFolders, files in os.walk(self.dirpath):
			dtype = None
			#frombup = set()
			if 'chaporder.dat' in files:
				filename = os.path.join(root, 'chaporder.dat')
				chaporder = ComicInfo(json.load(open(filename, 'r')))
				logging.info(str(chaporder))
				tempid = self.basename(root)
				if tempid.isdigit():
					tempid = int(tempid)
					if tempid == chaporder.comicid:
						dtype = dtype or ('comic', chaporder.comicname)
					elif tempid in chaporder.chap:
						dtype = dtype or ('chap', chaporder.comicname, chaporder.renamef(tempid))
					elif chaporder.comicid is None:
						dtype = dtype or ('comic', chaporder.comicname)
						chaporder.comicid = tempid
				self.updatecomicdict(chaporder)
			for name in files:
				filename = os.path.join(root, name)
				if detectfile(filename) == 'buka' and not subFolders and (name == 'pack.dat' or len(files)<4):
					# only a buka (and a chaporder) (and an index2)
					logging.info('正在提取 ' + self.cutname(filename))
					buka = BukaFile(filename)
					logging.info(str(buka))
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						tempid = self.basename(root)
						if tempid.isdigit():
							tempid = int(tempid)
							dtype = dtype or ('chap', buka.comicname, chaporder.renamef(tempid))
					elif buka.comicid in self.comicdict:
						dtype = dtype or ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid))
					extractndecode(buka, root, self.dwebpman)
					buka.close()
					removefiles.append(filename)
				elif detectfile(filename) == 'buka':
					logging.info('正在提取 ' + self.cutname(filename))
					buka = BukaFile(filename)
					logging.info(str(buka))
					sp = splitpath(self.cutname(os.path.join(root, os.path.splitext(name)[0])))
					if buka.chapinfo:
						chaporder = buka.chapinfo
						self.updatecomicdict(chaporder)
						self.nodes[sp] = ('chap', buka.comicname, chaporder.renamef(buka.chapid))
					elif buka.comicid in self.comicdict:
						self.nodes[sp] = ('chap', buka.comicname, self.comicdict[buka.comicid].renamef(buka.chapid))
					extractndecode(buka, os.path.join(root, os.path.splitext(name)[0]), self.dwebpman)
					tempid = self.basename(root)
					if tempid.isdigit():
						tempid = int(tempid)
						if tempid == buka.comicid:
							dtype = dtype or ('comic', buka.comicname)
					buka.close()
					removefiles.append(filename)
				elif detectfile(filename) == 'bup':
					basename = os.path.splitext(filename)[0]
					with open(filename, 'rb') as f:
						f.seek(64)
						bupfile = f.read()
					# Don't use JPG files to cheat me!!!!!
					#trueformat = detectfile(basename + '.webp', True)
					trueformat = detectfile(bupfile, True)
					if trueformat == 'webp':
						logging.info('加入队列 ' + self.cutname(filename))
						#frombup.add(basename + '.webp')
						self.dwebpman.add(basename, bupfile, self.cutname(filename))
						#decodewebp(basename)
					else:
						with open('%s.%s' % (basename, trueformat), 'wb') as w:
							w.write(bupfile)
						logging.info('完成转换 ' + self.cutname(filename))
					removefiles.append(filename)
				elif detectfile(filename) == 'tmp':
					logging.info('已忽略 ' + self.cutname(filename))
					removefiles.append(filename)
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
					except Exception:
						logging.error('不是有效的数据库: ' + self.cutname(filename))
				#else:
					#dtype = 'unk'
			#for name in subFolders:
				#pass
			if root == self.dirpath:
				rootdir = self.origpath
			else:
				rootdir = root
			sp = splitpath(self.cutname(root))
			if not dtype:
				tempid = self.basename(rootdir)
				if tempid.isdigit():
					tempid = int(tempid)
					if tempid in self.comicdict:
						dtype = ('comic', self.comicdict[tempid].comicname)
					else:
						tempid2 = self.basename(os.path.dirname(root))
						if tempid2.isdigit():
							tempid2 = int(tempid2)
							if tempid2 in self.comicdict:
								if tempid in self.comicdict[tempid2].chap:
									dtype = ('chap', self.comicdict[tempid2].comicname, self.comicdict[tempid2].renamef(tempid))
			self.nodes[sp] = dtype
		# just for the low speed of Windows
		for filename in removefiles:
			tryremove(filename)

	def renamedirs(self):
		'''Does the renaming.'''
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
	'''Avoid conflicts when moving into an exist directory.'''
	if src == dst:
		pass
	elif os.path.isdir(src) and os.path.isdir(dst):
		for item in os.listdir(src):
			movedir(os.path.join(src, item), os.path.join(dst, item))
		os.rmdir(src)
	else:
		delayedtry(shutil.move, src, dst)

def delayedtry(fn, *args, **kwargs):
	for att in range(10):
		try:
			fn(*args, **kwargs)
			break
		except Exception as ex:
			logging.debug("Try failed, trying... " + str(att+1))
			if att == 9:
				logging.error("文件操作失败超过重试次数。")
				raise ex
			time.sleep(0.2 * att)

def tryremove(filename):
	'''
	Tries to remove a file until it's not locked.

	It's just for the LOW speed of Windows.
	The exceptions are caused by the file lock is not released by System(4)
	'''
	for att in range(10):
		try:
			os.remove(filename)
			break
		except PermissionError as ex:
			logging.debug("Delete failed, trying... " + str(att+1))
			if att == 9:
				logging.error("删除文件失败超过重试次数。")
				raise ex
			time.sleep(0.2 * att)

def splitpath(path):
	'''
	Splits a path to a list.
	>>> p = splitpath('a/b/c/d/')
	# p = ['a', 'b', 'c', 'd']
	>>> p = splitpath('/a/b/c/d')
	# p = ['/', 'a', 'b', 'c', 'd']
	'''
	folders = []
	path = path.rstrip('\\/')
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
	'''Extracts buka files and puts decode requests.'''
	if not os.path.exists(path):
		os.makedirs(path)
	for key in bukafile.files:
		if os.path.splitext(key)[1] == '.bup':
			#with open(os.path.join(path, os.path.splitext(key)[0] + '.webp'), 'wb') as f:
				#f.write(bukafile.getfile(key, 64))
			dwebpman.add(os.path.join(path, os.path.splitext(key)[0]), bukafile.getfile(key, 64), os.path.join(os.path.basename(path), key))
		elif key == 'logo':
			with open(os.path.join(path, key + '.jpg'), 'wb') as f:
				f.write(bukafile[key])
		else:
			with open(os.path.join(path, key), 'wb') as f:
				f.write(bukafile[key])

def buildfromdb(dbname):
	'''
	Build a dict of BukaFile objects from buka_store.sql file in iOS devices.
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
	return dict((k, ComicInfo(v, k)) for k,v in d.items())

def detectfile(filename, force=False):
	'''
	Tests file format.

	Parts from standard library imghdr.
	'''
	if isinstance(filename, str):
		if not os.path.exists(filename):
			return None
		if os.path.isdir(filename):
			return 'dir'
		if not os.path.isfile(filename):
			return False
		if not force:
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
			elif ext == '.tmp':
				return 'tmp'
		with open(filename, 'rb') as f:
			h = f.read(32)
	elif isinstance(filename, bytes):
		h = filename[:32]
	else:
		h = filename.peek(32)
	if h[6:10] in (b'JFIF', b'Exif'):
		return 'jpg'
	elif h[:4] == b"bup\x00":
		return 'bup'
	elif h[:4] == b"RIFF" and h[8:16] == b"WEBPVP8 ":
		return 'webp'
	elif h[:4] == b"buka":
		return 'buka'
	elif h[:4] == b"AKUB" or h[12:16] == b"AKUB":
		return 'index2'
	elif h.startswith(b'SQLite format 3'):
		return 'sqlite3'
	# IMHO Buka won't be that crazy to use other formats.
	elif h.startswith(b'\211PNG\r\n\032\n'):
		return 'png'
	elif h[:6] in (b'GIF87a', b'GIF89a'):
		return 'gif'
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
		elif detectfile(s) in ('index2','chaporder','buka','bup','jpg','png','sqlite3'): # whitelist ,'webp'
			if os.path.splitext(s)[1] == '.view':
				d = os.path.splitext(d)[0]
			if not os.path.isfile(d) or os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
				shutil.copy2(s, d)
	if not os.listdir(dst):
		os.rmdir(dst)

class DwebpMan:
	'''
	Use a pool of dwebp's to decode webps.
	'''
	def __init__(self, dwebppath=None, process=1, pilconvert=False, quality=92):
		'''
		If dwebppath is False, don't convert.
		'''
		self.pilconvert = pilconvert
		self.quality = quality
		programdir = os.path.dirname(os.path.abspath(sys.argv[0]))
		self.fail = False
		if '64' in platform.machine():
			bit = '64'
		else:
			bit = '32'
		logging.debug('platform.machine() = %s', platform.machine())
		if dwebppath is False:
			self.supportwebp = False
			self.dwebp = None
			self.pool = None
			return
		elif dwebppath:
			self.dwebp = dwebppath
		elif os.name == 'nt' or sys.platform in ('win32', 'cygwin'):
			self.dwebp = os.path.join(programdir, 'dwebp_' + bit + '.exe')
		elif sys.platform == 'darwin':
			self.dwebp = os.path.join(programdir, 'dwebp_mac')
		else:
			self.dwebp = os.path.join(programdir, 'dwebp_' + bit)

		DEVNUL = open(os.devnull, 'w')
		try:
			p = Popen(self.dwebp, stdout=DEVNUL, stderr=DEVNUL).wait()
			self.supportwebp = True
		except Exception as ex:
			if os.name == 'posix':
				try:
					p = Popen('dwebp', stdout=DEVNUL, stderr=DEVNUL).wait()
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
		DEVNUL.close()
		logging.debug("dwebp = " + self.dwebp)
		if self.supportwebp:
			self.pool = threadpool.NoOrderedRequestManager(process, self.decodewebp, self.checklog, self.handle_thread_exception, q_size=10)
		else:
			self.pool = None

	def __repr__(self):
		return "<DwebpMan supportwebp=%r dwebp=%r>" % (self.supportwebp, self.dwebp)

	def add(self, basepath, webpfile, displayname):
		'''Ignores if not supported.'''
		if self.pool:
			self.pool.putRequest(basepath, webpfile, displayname)
		else:
			with open(basepath + '.webp', 'wb') as f:
				f.write(webpfile)

	def wait(self):
		self.pool.wait()

	def checklog(self, request, result):
		if 'Saved' not in result[1]:
			logging.error("dwebp 错误[%d]: %s", result[0], result[1])
			self.fail = True
		else:
			logging.info("完成转换 %s", request.args[2])
			logging.debug("dwebp OK[%d]: %s", result[0], result[1])

	def handle_thread_exception(self, request, exc_info):
		"""Logging exception handler callback function."""
		self.fail = True
		logging.getLogger().error(str(request))
		traceback.print_exception(*exc_info, file=logstr)

	def decodewebp(self, basepath, webpfile, displayname):
		if self.pilconvert:
			proc = Popen([self.dwebp, "-bmp", "-o", "-", "--", "-"], stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=os.getcwd())
			stdout, stderr = proc.communicate(webpfile)
			if stdout:
				self.convertpng(basepath, stdout)
			else:
				# This will handled using stderr info.
				pass
		else:
			proc = Popen([self.dwebp, "-o", basepath + ".png", "--", "-"], stdin=PIPE, stdout=PIPE, stderr=PIPE, cwd=os.getcwd())
			stdout, stderr = proc.communicate(webpfile)
		#tryremove(basepath + ".webp")
		if stderr:
			stderr = stderr.decode(errors='ignore')
		return (proc.returncode, stderr)

	def convertpng(self, basepath, imgdata):
		im = Image.open(BytesIO(imgdata))
		im.save(basepath + '.jpg', quality=self.quality)
		im.close()
		del im

class DwebpPILMan:
	"""
	Use threads of PIL.Image instead of dwebp to decode webps.

	Note: For now, this class is available for decoding, and the it's faster.
	      BUT, use this for decoding hundreds of images will cause CPython
	      memory leaks. gc / del / close() don't work. Using multiprocessing
	      is a waste though. This is caused by a webp handling bug in Pillow.
	      So, don't use it for a large number of images.
	      If you can fix it, contact the __author__.
	"""
	def __init__(self, process=1, quality=92):
		self.quality = quality
		self.supportwebp = True
		self.fail = False
		self.pool = threadpool.NoOrderedRequestManager(process, self.decodewebp, self.checklog, self.handle_thread_exception, q_size=10)

	def add(self, basepath, webpfile, displayname):
		self.pool.putRequest(basepath, webpfile, displayname)

	def wait(self):
		self.pool.wait()

	def checklog(self, request, result):
		if result:
			logging.info("完成转换 %s", request.args[2])
		else:
			logging.error("解码错误: %s", request.args[2])

	def handle_thread_exception(self, request, exc_info):
		"""Logging exception handler callback function."""
		self.fail = True
		logging.getLogger().error(str(request))
		traceback.print_exception(*exc_info, file=logstr)

	def decodewebp(self, basepath, webpfile, displayname):
		try:
			im = Image.open(BytesIO(webpfile))
			im.save(basepath + '.jpg', quality=self.quality)
			im.close()
			del im
			#tryremove(basepath + ".webp")
			return True
		except Exception as ex:
			if 'image' in repr(ex):
				logging.getLogger().debug('%s %s' % (basepath, repr(ex)))
				traceback.print_exception(*sys.exc_info(), file=logstr)
				return False
			else:
				raise ex

class DwebpSingleThreadPILMan:
	"""
	Use PIL.Image instead of dwebp to decode webps, using the main thread.
	
	Note: This also suffers from the memory leak caused by a webp handling
	      bug in Pillow.
	"""
	def __init__(self, process=1, quality=92):
		self.quality = quality
		self.supportwebp = True
		self.fail = False

	def add(self, basepath, webpfile, displayname):
		result = self.decodewebp(basepath, webpfile, displayname)
		if not result:
			self.fail = True
			logging.error("解码错误: %s", displayname)
		else:
			logging.info("完成转换 %s", displayname)

	def wait(self):
		pass

	def decodewebp(self, basepath, webpfile, displayname):
		try:
			im = Image.open(BytesIO(webpfile))
			im.save(basepath + '.jpg', quality=self.quality)
			im.close()
			del im
			#tryremove(basepath + ".webp")
			return True
		except Exception as ex:
			if 'image' in repr(ex):
				logging.getLogger().debug('%s %s' % (basepath, repr(ex)))
				traceback.print_exception(*sys.exc_info(), file=logstr)
				return False
			else:
				raise ex

def logexit(err=True, wait=True):
	logging.shutdown()
	try:
		with open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])),'bukaex.log'), 'a') as f:
			f.write(logstr.getvalue())
	except Exception:
		with open('bukaex.log', 'a') as f:
			f.write(logstr.getvalue())
	if err:
		print('如果不是使用方法错误，请发送错误报告 bukaex.log 给作者 ' + __author__)
	if wait and os.name == 'nt':
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
		cpus = max(cpu_count()//2 if cpu_count() else 1, 1)
	except NotImplementedError:
		cpus = 1

	logging.info('%s version %s' % (os.path.basename(sys.argv[0]), __version__))
	parser = ArgumentParserWait(description="Converts comics downloaded by Buka.")
	parser.add_argument("-p", "--process", help="The max number of running dwebp's. (Default = CPU count)", default=cpus, type=int, metavar='NUM')
	# parser.add_argument("-s", "--same-dir", action='store_true', help="Change the default output dir to <input>/../output. Ignored when specifies <output>")
	parser.add_argument("-c", "--current-dir", action='store_true', help="Change the default output dir to ./output. Ignored when specifies <output>")
	parser.add_argument("-l", "--log", action='store_true', help="Force logging to file.")
	parser.add_argument("-n", "--keepwebp", action='store_true', help="Keep WebP, don't convert them.")
	parser.add_argument("--pil", action='store_true', help="Perfer PIL/Pillow for decoding, faster, and may cause memory leaks.")
	parser.add_argument("--dwebp", help="Locate your own dwebp WebP decoder.", default=None)
	parser.add_argument("-q", "--quality", help="JPG quality. (Default = 92)", default=92, type=int, metavar='NUM')
	parser.add_argument("-d", "--db", help="Locate the 'buka_store.sql' file in iOS devices, which provides infomation for renaming.", default=None, metavar='buka_store.sql')
	parser.add_argument("--debug", action='store_true', help=argparse.SUPPRESS)
	parser.add_argument("input", help="The .buka file or the folder containing files downloaded by Buka, which is usually located in (Android) /sdcard/ibuka/down")
	parser.add_argument("output", nargs='?', help="The output folder. (Default = ./output)", default=None)
	args = parser.parse_args()
	if args.debug:
		for hdlr in logging.getLogger().handlers:
			hdlr.setLevel(logging.DEBUG)
	logging.debug(repr(args))

	programdir = os.path.dirname(os.path.abspath(sys.argv[0]))
	fn_buka = args.input.rstrip('\\/')
	if args.output:
		target = args.output
	elif args.current_dir:
		target = 'output'
	else:
		target = os.path.join(os.path.dirname(fn_buka), 'output')
	target = os.path.abspath(target)
	logging.info('输出至 ' + target)
	if not os.path.exists(target):
		os.makedirs(target)
	dbdict = {}
	if args.db:
		try:
			dbdict = buildfromdb(args.db)
		except Exception:
			logging.error('指定的数据库文件不是有效的 iOS 设备中的 buka_store.sql 数据库文件。提取过程将继续。')

	logging.info("检查环境...")
	#logging.debug(repr(os.uname()))
	logging.debug('SUPPORTPIL = %r' % SUPPORTPIL)
	if args.keepwebp:
		dwebpman = DwebpMan(False, args.process, SUPPORTPIL, args.quality)
	elif args.dwebp:
		dwebpman = DwebpMan(args.dwebp, args.process, SUPPORTPIL, args.quality)
	elif SUPPORTPIL and args.pil:
		dwebpman = DwebpPILMan(args.process, args.quality)
		# dwebpman = DwebpSingleThreadPILMan(args.process)
	else:
		dwebpman = DwebpMan(args.dwebp, args.process, SUPPORTPIL, args.quality)
	logging.debug("dwebpman = %r" % dwebpman)

	if os.path.isdir(target):
		if detectfile(fn_buka) == "buka":
			if not os.path.isfile(fn_buka):
				logging.critical('没有此文件: ' + fn_buka)
				if not os.listdir(target):
					os.rmdir(target)
				logexit()
			logging.info('正在提取 ' + fn_buka)
			buka = BukaFile(fn_buka)
			logging.info(str(buka))
			extractndecode(buka, target, dwebpman)
			if dwebpman.supportwebp:
				dwebpman.wait()
			if buka.chapinfo:
				movedir(target, os.path.join(os.path.dirname(target), "%s-%s" % (buka.comicname, buka.chapinfo.renamef(buka.chapid))))
			else:
				# cannot get chapter name
				movedir(target, os.path.join(os.path.dirname(target), "%s-%s" % (buka.comicname, buka.chapid)))
			buka.close()
		elif os.path.isdir(fn_buka):
			logging.info('正在复制...')
			copytree(fn_buka, target)
			dm = DirMan(target, dwebpman, fn_buka, dbdict)
			dm.detectndecode()
			if dwebpman.supportwebp:
				logging.info("等待所有转换进程/线程...")
				dwebpman.wait()
			logging.info("完成转换。")
			logging.info("正在重命名...")
			dm.renamedirs()
		else:
			logging.critical("输入必须为 buka 文件或一个文件夹。")
			if not os.listdir(target):
				os.rmdir(target)
			logexit()
		if dwebpman.fail:
			logexit()
		logging.info('完成。')
		if not args.keepwebp and not dwebpman.supportwebp:
			logging.warning('警告: .bup 格式保留为 WebP 格式，没有转换为普通图片。')
			logexit()
		if args.log:
			logexit(False, False)
	else:
		logging.critical("错误: 输出文件夹路径为一个文件。")
		logexit()

if __name__ == '__main__':
	try:
		main()
	except SystemExit:
		pass
	except KeyboardInterrupt:
		logexit(False, False)
	except Exception:
		logging.exception('错误: 主线程异常退出。')
		logexit()
