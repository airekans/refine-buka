#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Python 3.x

__author__ = "Gumble <abcdoyle888@gmail.com>"
__version__ = "2.0"

'''
布卡漫画转换工具
支持 .buka, .bup.view, .jpg.view

漫画目录 存放在 /sdcard/ibuka/down
'''

import sys
import os
import shutil
import argparse
import time
import json
import struct
import sqlite3
import logging
from io import StringIO
from subprocess import Popen
from platform import machine

NT_SLEEP_SEC = 6
logstr = StringIO()
logging.basicConfig(format='%(levelname)s:%(funcName)s:%(message)s', level=logging.DEBUG, stream=logstr)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)-8s %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

class BadBukaFile(Exception):
	pass

class ArgumentParserWait(argparse.ArgumentParser):
	def exit(self, status=0, message=None):
		if message:
			self._print_message(message, sys.stderr)
		if os.name == 'nt':
			time.sleep(NT_SLEEP_SEC)
		sys.exit(status)

class tTree():
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
	def __init__(self, filename):
		'''Reads the buka file.'''
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
		self.files = {}
		pos = 0
		while pos+8 < len(buff):
			pointer, size = struct.unpack('<II', buff[pos:pos + 8])
			pos += 8
			end = buff.find(b'\x00', pos)
			name = buff[pos:end].decode(encoding='utf-8', errors='ignore')
			pos = end + 1
			self.files[name] = (pointer, size)
	
	def __len__(self):
		return len(self.files)
	
	def __getitem__(self, key):
		if key in self.files:
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
			return cid
	
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
	def __init__(self, dirpath, comicdict={}):
		self.dirpath = dirpath
		self.nodes = tTree()
		self.comicdict = comicdict
	
	def __repr__(self):
		return "<DirMan dirpath=%r>" % self.dirpath
	
	def updatecomicdict(self, comicinfo):
		if comicinfo.comicid in self.comicdict:
			self.comicdict[comicinfo.comicid].chaporder.update(comicinfo.chaporder)
			self.comicdict[comicinfo.comicid].chap.update(comicinfo.chap)
		else:
			self.comicdict[comicinfo.comicid] = comicinfo
	
	def detectndecode(self):
		ifndef = lambda x,y: x if x else y
		for root, subFolders, files in os.walk(self.dirpath):
			dtype = None
			for name in files:
				if name == 'chaporder.dat':
					chaporder = ComicInfo(json.load(open(os.path.join(root, name), 'r')))
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
				#elif name == 'index2.dat':
					#pass
				elif os.path.splitext(name)[1] == '.buka':
					buka = BukaFile(os.path.join(root, name))
					chaporder = ComicInfo(json.loads(buka['chaporder.dat'].decode('utf-8')))
					if chaporder.comicid is None:
						chaporder.comicid = int(os.path.basename(root))
					self.updatecomicdict(chaporder)
					extractndecode(buka, os.path.join(root, os.path.splitext(name)[0]))
					dtype = ifndef(dtype, ('comic', buka.comicname))
					del buka
					os.remove(os.path.join(root, name))
				elif name == 'pack.dat':
					buka = BukaFile(os.path.join(root, name))
					chaporder = ComicInfo(json.loads(buka['chaporder.dat'].decode('utf-8')))
					self.updatecomicdict(chaporder)
					# buka.extractall(root)
					extractndecode(buka, root)
					dtype = ifndef(dtype, ('chap', buka.comicname, chaporder.renamef(int(os.path.basename(root)))))
					del buka
					os.remove(os.path.join(root, name))
				elif os.path.splitext(name)[1] == '.webp':
					decodewebp(os.path.join(path, os.path.splitext(name)[0]))
					#dtype = 'chap'
				elif name == 'buka_store.sql':
					cdict = buildfromdb(os.path.join(root, name))
					for key in cdict:
						self.updatecomicdict(cdict[key])
				#else:
					#dtype = 'unk'
			for name in subFolders:
				pass
			sp = splitpath(root.lstrip(os.path.dirname(self.dirpath)))
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
	
	def renamedirs(self):
		ls = sorted(self.nodes.keys(), key=len, reverse=True)
		for i in ls:
			this = self.nodes.get(i)
			parent = self.nodes.get(i[:-1])
			if this:
				origpath = os.path.join(os.path.dirname(self.dirpath), *i)
				basepath = os.path.join(os.path.dirname(self.dirpath), *i[:-1])
				if this[0] == 'comic':
					shutil.move(origpath, os.path.join(basepath, this[1]))
				elif parent:
					if this[1] == parent[1]:
						shutil.move(origpath, os.path.join(basepath, this[2]))
				else:
					shutil.move(origpath, os.path.join(basepath, this[1] + '-' + this[2]))

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

def extractndecode(bukafile, path):
	if not os.path.exists(path):
		os.makedirs(path)
	for key in bukafile.files:
		if os.path.splitext(key)[1] == '.bup':
			with open(os.path.join(path, os.path.splitext(key)[0] + '.webp'), 'wb') as f:
				f.write(bukafile.getfile(key,64))
			decodewebp(os.path.join(path, os.path.splitext(key)[0]))
			##### use tpool
		elif key == 'logo':
			with open(os.path.join(path, key + '.jpg'), 'wb') as f:
				f.write(bukafile[key])
		else:
			with open(os.path.join(path, key), 'wb') as f:
				f.write(bukafile[key])

def buildfromdb(dbname):
	'''Build a dict of BukaFile objects from buka_store.sql file in
	   iOS devices.'''
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
			 #'links': [{'cid': '0', #chapterinfo/cid
						#'idx': '0', #chapterinfo/idx
						#'ressupport': '7',
						#'size': '0',
						#'title': '', #chapterinfo/title if not chapterinfo/fulltitle else ''
						#'type': '0' #'卷' in chapterinfo/fulltitle : 0; '话':1; not chapterinfo/fulltitle: 2
						#}],
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
	if filename == 'index2.dat':
		return 'index2'
	elif filename == 'chaporder.dat':
		return 'chaporder'
	ext = os.path.splitext(filename)[1]
	if ext == 'buka':
		return 'buka'
	elif ext == 'bup':
		return 'bup'
	elif ext == 'view':
		ext2 = os.path.splitext(os.path.splitext(filename)[0])[1]
		if ext2 == 'jpg':
			return 'jpg'
		elif ext2 == 'bup':
			return 'bup'
		elif ext2 == 'png':
			return 'png'
	with open(filename, 'rb'):
		h = f.read(32)
	if h[6:10] in (b'JFIF', b'Exif'):
		return 'jpg'
	elif h.startswith(b'\211PNG\r\n\032\n'):
		return 'png'
	elif h[:4] == b"buka":
		return 'buka'
	elif h[:4] == b"AKUB":
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
		# if os.path.isfile(s) and (os.path.splitext(s)[1] not in [".view", ".buka"]) and item != 'chaporder.dat':
			# continue
		if os.path.isdir(s):
			copytree(s, d, symlinks, ignore)
		else:
			# if os.path.isfile(os.path.join(dst, os.path.splitext(item)[0])):
				# continue
			if os.path.splitext(s)[1] == '.view':
				d = os.path.splitext(d)[0]
			if not os.path.isfile(d) or os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
				shutil.copy2(s, d)

def decodewebp(basepath):
	#rc = Popen([dwebp, basepath + ".webp", "-o", basepath + ".png"], cwd=os.getcwd()).wait()
	return 0
	#os.remove(basepath + ".webp")
	return rc

def checkdwebp(dwebppath=None):
	programdir = os.path.dirname(os.path.abspath(sys.argv[0]))
	if '64' in machine():
		bit = '64'
	else:
		bit = '32'
	logging.debug('machine type: %s', machine())
	if dwebppath:
		dwebp = dwebppath
	elif os.name == 'nt':
		dwebp = os.path.join(programdir, 'dwebp_' + bit + '.exe')
	else:
		dwebp = os.path.join(programdir, 'dwebp_' + bit)
	
	nul = open(os.devnull, 'w')
	try:
		p = Popen(dwebp, stdout=nul, stderr=nul).wait()
		supportwebp = True
	except Exception as ex:
		if os.name == 'posix':
			try:
				p = Popen('dwebp', stdout=nul, stderr=nul).wait()
				supportwebp = True
				dwebp = 'dwebp'
				logging.info("used dwebp installed in the system.")
			except Exception as ex:
				logging.error("dwebp 不可用，仅支持普通文件格式。")
				logging.debug("dwebp test: " + repr(ex))
				supportwebp = False
		else:
			logging.error("dwebp 不可用，仅支持普通文件格式。")
			logging.debug("dwebp test: " + repr(ex))
			supportwebp = False
	nul.close()
	logging.debug("dwebp = " + dwebp)
	return (supportwebp, dwebp)

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
		sys.exit()
	

def main():
	if sys.version_info[0] < 3:
		logging.critical('要求 Python 3.')
		logexit(False)

	parser = ArgumentParserWait(description="Converts comics downloaded by Buka.")
	parser.add_argument("-p", help="the max number of running dwebp's. (Default = CPU count)", default=os.cpu_count(), type=int, metavar='PROCESSES')
	parser.add_argument("-dwebp", help="locate your own dwebp WebP decoder.", default=None)
	parser.add_argument("-db", help="locate the 'buka_store.sql' file in iOS devices, which provides infomation for renaming.", default=None, metavar='buka_store.sql')
	parser.add_argument("input", help="the .buka file or the folder containing files downloaded by Buka, which is usually located in (Android) /sdcard/ibuka/down")
	parser.add_argument("output", nargs='?', help="the output folder. (Default in ./output)", default='output')
	args = parser.parse_args()
	logging.debug(repr(args))

	fn_buka = args.input
	target = args.output
	if not os.path.exists(target):
		shutil.makedirs(target)
	programdir = os.path.dirname(os.path.abspath(sys.argv[0]))

	if os.name == 'nt':
		dwebp = os.path.join(programdir, 'dwebp.exe')
	else:
		dwebp = os.path.join(programdir, 'dwebp')

	logging.info("检查环境...")
	supportwebp, dwebp = checkdwebp(args.dwebp)

	if os.path.isdir(target):
		if detectfile(fn_buka) == "buka":
			if not os.path.isfile(fn_buka):
				logging.critical('没有此文件: ' + fn_buka)
				if not os.listdir(target):
					os.rmdir(target)
				logexit()
			logging.info('正在提取 ' + fn_buka)
			extractbuka(fn_buka, target)
			if os.path.isfile(os.path.join(target, "chaporder.dat")):
				dat = json.loads(open(os.path.join(target, "chaporder.dat"), 'r').read())
				os.remove(os.path.join(target, "chaporder.dat"))
				chap = build_dict(dat['links'], 'cid')
				newtarget = os.path.join(os.path.dirname(target), dat['name'] + '-' + renamef(chap, os.path.basename(os.path.splitext(fn_buka)[0])))
				shutil.move(target, newtarget)
				target = newtarget
		elif os.path.isdir(fn_buka):
			logging.info('正在复制...')
			copytree(fn_buka, target)
		else:
			logging.critical("输入必须为 buka 文件或一个文件夹。")
			logexit()
		allfile = []
		dwebps = []
		for root, subFolders, files in os.walk(target):
			for name in files:
				fpath = os.path.join(root, name)
				if os.path.splitext(fpath)[1] == ".buka":
					logging.info('正在提取 ' + fpath)
					extractbuka(fpath, os.path.splitext(fpath)[0])
					chaporder = os.path.join(os.path.splitext(fpath)[0], "chaporder.dat")
					if os.path.isfile(chaporder):
						dat = json.loads(open(chaporder, 'r').read())
						os.remove(chaporder)
						chap = build_dict(dat['links'], 'cid')
						shutil.move(os.path.splitext(fpath)[0], os.path.join(os.path.dirname(fpath), renamef(chap, os.path.basename(os.path.splitext(fpath)[0]))))
					os.remove(fpath)
		for root, subFolders, files in os.walk(target):
			for name in files:
				allfile.append(os.path.join(root, name))
		for fpath in allfile:
			logging.info('正在提取 ' + fpath)
			if os.path.splitext(fpath)[1] in (".view", ".bup"):
				if os.path.splitext(fpath)[1] == ".view":
					bupname = os.path.splitext(fpath)[0]
				else:
					bupname = fpath
				basepath = os.path.splitext(bupname)[0]
				if os.path.splitext(bupname)[1] == ".bup":
					if supportwebp:
						with open(fpath, "rb") as bup, open(basepath + ".webp", "wb") as webp:
							bup.read(64)  # and eat it
							shutil.copyfileobj(bup, webp)
						os.remove(fpath)
						p = Popen([dwebp, basepath + ".webp", "-o", os.path.splitext(basepath)[0] + ".png"], cwd=os.getcwd())  # .wait()  faster
						time.sleep(0.2)  # prevent creating too many dwebp's
						if not p.poll():
							dwebps.append(p)
					else:
						os.remove(fpath)
				else:
					shutil.move(fpath, bupname)
			# else:	pass
		if dwebps:
			logging.info("等待所有 dwebp 转换进程...")
			for p in dwebps:
				p.wait()
		logging.info("完成转换。")
		logging.info("正在重命名...")
		alldir = []
		for root, subFolders, files in os.walk(target):
			for name in files:
				if os.path.splitext(name)[1] == ".webp":
					os.remove(os.path.join(root, name))
			for name in subFolders:
				alldir.append((root, name))
		alldir.append(os.path.split(target))
		for dirname in alldir:
			fpath = os.path.join(dirname[0], dirname[1])
			if os.path.isfile(os.path.join(fpath, "chaporder.dat")):
				dat = json.loads(open(os.path.join(fpath, "chaporder.dat"), 'r').read())
				os.remove(os.path.join(fpath, "chaporder.dat"))
				chap = build_dict(dat['links'], 'cid')
				for item in os.listdir(fpath):
					if os.path.isdir(os.path.join(fpath, item)):
						shutil.move(os.path.join(fpath, item), os.path.join(fpath, renamef(chap, item)))
				shutil.move(fpath, os.path.join(dirname[0], dat['name']))
		if not supportwebp:
			logging.warning('警告: .bup 格式文件无法提取。')
		logging.info('完成。')
	else:
		logging.critical("错误: 输出文件夹路径为一个文件。")
		logexit()

if __name__ == '__main__':
	main()

