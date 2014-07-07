#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from PIL import Image

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

def main():
	for root, subFolders, files in os.walk(sys.argv[1]):
		for name in files:
			if os.path.splitext(name)[1] == '.png':
				print(os.path.join(root, name))
				im = Image.open(os.path.join(root, name))
				im.save(os.path.splitext(os.path.join(root, name))[0] + '.jpg', quality=90)
				im.close()
				del im
				tryremove(os.path.join(root, name))

if __name__ == '__main__':
	main()

