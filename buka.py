#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Python 3.3 compatible with Python 2.7
'''
布卡漫画转换工具
支持 .buka, .bup.view, .jpg.view

漫画目录 存放在 /sdcard/ibuka/down
'''

import sys,os,shutil,time,json,re,struct
from subprocess import Popen

helpm = '''Extract mangas downloaded by Buka.

usage: python3 %s input [output]

positional argument:
 input       the .buka file or a directory contains downloaded files.
             usually it's in (Android) /sdcard/ibuka/down

optional argument:
 output      the target directory.(=the current dir.)
''' % sys.argv[0]

if len(sys.argv)==2:
	target = os.path.join(os.path.dirname(sys.argv[1]),"output")
	if not os.path.exists(target):
		os.mkdir(target)
elif len(sys.argv)==3:
	target = sys.argv[2]
else:
	print(helpm)
	sys.exit()

fn_buka = sys.argv[1]

if os.name=='nt':
	dwebp = 'dwebp.exe'
else:
	dwebp = './dwebp'

#JPG
#開頭 FFD8
#結尾 FFD9

def copytree(src, dst, symlinks=False, ignore=None):
	if not os.path.exists(dst):
		os.makedirs(dst)
	for item in os.listdir(src):
		s = os.path.join(src, item)
		d = os.path.join(dst, item)
		if os.path.isfile(s) and (os.path.splitext(s)[1] not in [".view",".buka"]) and item!='chaporder.dat':
			continue
		if os.path.isdir(s):
			copytree(s, d, symlinks, ignore)
		else:
			if not os.path.exists(d) or os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
				shutil.copy2(s, d)

def build_dict(seq, key):
	rd={}
	for d in seq:
		rd[d[key]]=d
	return rd

def renamef(chap,cid):
	if chap.get(cid):
		if chap[cid]['title']:
			return chap[cid]['title']
		else:
			if chap[cid]['type']=='0':
				return u'卷'+ chap[cid]['idx'].zfill(2)
			elif chap[cid]['type']=='1':
				return u'第'+ chap[cid]['idx'].zfill(3)+ u'话'
			elif chap[cid]['type']=='2':
				return u'番外'+ chap[cid]['idx'].zfill(2)
			else:
				return chap[cid]['idx'].zfill(3)
	else:
		return cid


def extractbuka(bkname, tgdir):
	if not os.path.exists(tgdir):
		os.mkdir(tgdir)
	with open(bkname, 'rb') as f:
		buff = f.read(16384)
		toc = re.findall(br'\x00([\x00-\xff]{8})[-_a-zA-Z0-9]*(\d{4}\.jpg)',buff)
		for index in toc:
			pos, size = struct.unpack('<II', index[0])
			img = open(os.path.join(tgdir,index[1].decode(encoding='UTF-8')),'wb')
			f.seek(pos)
			data = f.read(size)
			img.write(data)
			img.close()

if os.path.isdir(target):
	if os.path.splitext(fn_buka)[1]==".buka":
		extractbuka(fn_buka,target)
	else:
		if os.path.isdir(fn_buka):
			print('Copying...')
			copytree(fn_buka, target)
			allfile=[]
			dwebps=[]
			for root, subFolders, files in os.walk(target):
				for name in files:
					allfile.append(os.path.join(root,name))
			for fpath in allfile:
				print('Extracting %s' % fpath)
				if os.path.splitext(fpath)[1]==".buka":
					extractbuka(fpath,os.path.splitext(fpath)[0])
					os.remove(fpath)
				elif os.path.splitext(fpath)[1]==".view":
					basepath = os.path.splitext(os.path.splitext(fpath)[0])[0]
					if os.path.splitext(os.path.splitext(fpath)[0])[1]==".bup":
						bup = open(fpath, "rb")
						webp = open(basepath + ".webp", "wb")
						bup.read(64)
						shutil.copyfileobj(bup, webp)
						bup.close()
						webp.close()
						os.remove(fpath)
						p=Popen([dwebp, basepath + ".webp", "-o" ,os.path.splitext(basepath)[0] + ".png"], cwd=os.getcwd()) #.wait()  faster
						time.sleep(0.25) #prevent creating too many dwebps
						if not p.poll():
							dwebps.append(p)
					else:
						shutil.move(fpath, os.path.splitext(fpath)[0])
				else:
					pass
			print("Waiting for all dwebp's...")
			for p in dwebps:
				p.wait()
			alldir=[]
			print("Convertion done.")
			print("Renaming...")
			for root, subFolders, files in os.walk(target):
				for name in files:
					if os.path.splitext(name)[1]==".webp":
						os.remove(os.path.join(root,name))
				for name in subFolders:
					alldir.append((root,name))
			for dirname in alldir:
				fpath = os.path.join(dirname[0],dirname[1])
				if os.path.isfile(os.path.join(fpath,"chaporder.dat")):
					dat=json.loads(open(os.path.join(fpath,"chaporder.dat"),'r').read())
					os.remove(os.path.join(fpath,"chaporder.dat"))
					chap=build_dict(dat['links'],'cid')
					for item in os.listdir(fpath):
						if os.path.isdir(os.path.join(fpath,item)):
							shutil.move(os.path.join(fpath,item),os.path.join(fpath,renamef(chap,item)))
					shutil.move(fpath,os.path.join(dirname[0],dat['name']))
			print('Done.')
		else:
			print("Input must be a .buka file or a folder.")
else:
	print("Output put must be a folder.")
