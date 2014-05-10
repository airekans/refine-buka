#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Python 3.x

__version__ = '1.6'

'''
布卡漫画转换工具
支持 .buka, .bup.view, .jpg.view

漫画目录 存放在 /sdcard/ibuka/down
'''

import sys, os, shutil, time, json, struct
from subprocess import Popen

helpm = '''Extract mangas downloaded by Buka.

usage: python3 %s input [output]

positional argument:
 input       the .buka file or a directory contains downloaded files.
             usually it's in (Android) /sdcard/ibuka/down

optional argument:
 output      the target directory.(= the current dir.)
''' % sys.argv[0]

if sys.version_info[0] < 3:
	print('Python 3 required.')
	if os.name=='nt':
		time.sleep(3)
	sys.exit()

if len(sys.argv)==2:
	if sys.argv[1] in ("-h", "--help"):
		print(helpm)
		if os.name=='nt':
			time.sleep(3)
		sys.exit()
	else:
		target = os.path.join(os.path.dirname(sys.argv[1]),"output")
		if not os.path.exists(target):
			os.mkdir(target)
elif len(sys.argv)==3:
	target = sys.argv[2]
else:
	print(helpm)
	if os.name=='nt':
		time.sleep(3)
	sys.exit()

fn_buka = sys.argv[1]
programdir = os.path.dirname(os.path.abspath(sys.argv[1]))

if os.name=='nt':
	dwebp = os.path.join(programdir, 'dwebp.exe')
else:
	dwebp = os.path.join(programdir, 'dwebp')

print("Checking environment...")
try:
	with open(os.devnull,'w') as nul:
		p = Popen(dwebp, stdout=nul, stderr=nul).wait()
	supportwebp = True
except Exception as ex:
	print("dwebp is not available, so only normal image files are supported.\n" + repr(ex))
	supportwebp = False

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
			if os.path.isfile(os.path.join(dst, os.path.splitext(item)[0])):
				continue
			elif not os.path.isfile(d) or os.stat(src).st_mtime - os.stat(dst).st_mtime > 1:
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
				return '卷'+ chap[cid]['idx'].zfill(2)
			elif chap[cid]['type']=='1':
				return '第'+ chap[cid]['idx'].zfill(3)+ '话'
			elif chap[cid]['type']=='2':
				return '番外'+ chap[cid]['idx'].zfill(2)
			else:
				return chap[cid]['idx'].zfill(3)
	else:
		return cid

def extractbuka(bkname, target):
	if not os.path.isfile(bkname):
		print('No such file: ' + bkname)
		return ''
	if not os.path.exists(target):
		os.mkdir(target)
	toc = []
	comicname = ''
	with open(bkname, 'rb') as f:
		buff = f.read(16384)
		pos = buff.find(b'\x00',20)
		comicname = buff[20:pos].decode(errors='ignore')
		pos+=1
		endhead = pos + struct.unpack('<I', buff[pos:pos+4])[0] - 1
		pos+=4
		while pos < endhead:
			pointer, size = struct.unpack('<II', buff[pos:pos+8])
			pos+=8
			end = buff.find(b'\x00',pos)
			name = buff[pos:end].decode(errors='ignore')
			pos = end + 1
			toc.append((pointer, size, name))
		for index in toc:
			img = open(os.path.join(target,index[2]),'wb')
			f.seek(index[0])
			img.write(f.read(index[1]))
			img.close()

if os.path.isdir(target):
	if os.path.splitext(fn_buka)[1]==".buka":
		if not os.path.isfile(fn_buka):
			print('No such file: ' + fn_buka)
			if not os.listdir(target):
				os.rmdir(target)
			if os.name=='nt':
				time.sleep(3)
			sys.exit()
		print(('Extracting %s' % fn_buka))
		extractbuka(fn_buka,target)
		if os.path.isfile(os.path.join(target,"chaporder.dat")):
			dat=json.loads(open(os.path.join(target,"chaporder.dat"),'r').read())
			os.remove(os.path.join(target,"chaporder.dat"))
			chap=build_dict(dat['links'],'cid')
			newtarget = os.path.join(os.path.dirname(target),dat['name']+'-'+renamef(chap,os.path.basename(os.path.splitext(fn_buka)[0])))
			shutil.move(target,newtarget)
			target = newtarget
	elif os.path.isdir(fn_buka):
		print('Copying...')
		copytree(fn_buka, target)
	else:
		print("Input must be a .buka file or a folder.")
	allfile=[]
	dwebps=[]
	for root, subFolders, files in os.walk(target):
		for name in files:
			fpath = os.path.join(root,name)
			if os.path.splitext(fpath)[1]==".buka":
				print(('Extracting %s' % fpath))
				extractbuka(fpath,os.path.splitext(fpath)[0])
				chaporder = os.path.join(os.path.splitext(fpath)[0], "chaporder.dat")
				if os.path.isfile(chaporder):
					dat=json.loads(open(chaporder,'r').read())
					os.remove(chaporder)
					chap=build_dict(dat['links'],'cid')
					shutil.move(os.path.splitext(fpath)[0],os.path.join(os.path.dirname(fpath),renamef(chap,os.path.basename(os.path.splitext(fpath)[0]))))
				os.remove(fpath)
	for root, subFolders, files in os.walk(target):
		for name in files:
			allfile.append(os.path.join(root,name))
	for fpath in allfile:
		print(('Extracting %s' % fpath))
		if os.path.splitext(fpath)[1] in (".view", ".bup"):
			if os.path.splitext(fpath)[1]==".view":
				bupname = os.path.splitext(fpath)[0]
			else:
				bupname = fpath
			basepath = os.path.splitext(bupname)[0]
			if os.path.splitext(bupname)[1]==".bup":
				if supportwebp:
					with open(fpath, "rb") as bup, open(basepath + ".webp", "wb") as webp:
						bup.read(64) # and eat it
						shutil.copyfileobj(bup, webp)
					os.remove(fpath)
					p=Popen([dwebp, basepath + ".webp", "-o" ,os.path.splitext(basepath)[0] + ".png"], cwd=os.getcwd()) #.wait()  faster
					time.sleep(0.2) #prevent creating too many dwebp's
					if not p.poll():
						dwebps.append(p)
				else:
					os.remove(fpath)
			else:
				shutil.move(fpath, bupname)
		# else:	pass
	if dwebps:
		print("Waiting for all dwebp's...")
		for p in dwebps:
			p.wait()
	print("Convertion done.")
	print("Renaming...")
	alldir=[]
	for root, subFolders, files in os.walk(target):
		for name in files:
			if os.path.splitext(name)[1]==".webp":
				os.remove(os.path.join(root,name))
		for name in subFolders:
			alldir.append((root,name))
	alldir.append(os.path.split(target))
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
	if not supportwebp:
		print('WARNING: .bup files are not extracted.')
	print('Done.')
else:
	print("Output put must be a folder.")
