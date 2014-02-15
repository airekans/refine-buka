import re
import struct
import os
import sys
import time
import json

USAGE = """
    python refine.py INPUT_DIR OUTPUT_DIR
"""

def refine(file_name,output_dir):
    if not os.path.isdir(output_dir):
        print(USAGE)
        raise IOError('output dir `%s` not found' %output_dir)
    with open(file_name, 'rb') as f:
        buff = f.read(10000)
        toc = re.findall(r'\x00([\x00-\xff]{8})[-_a-zA-Z0-9]*(\d{4}\.jpg)',buff)
        for index in toc:
            pos, size = struct.unpack('<II', index[0])
            img = open(os.path.join(output_dir,index[1]),'wb')
            f.seek(pos)
            data =  f.read(size)
            img.write(data)
            img.close()

def extract_dir(input_dir, output_dir):
    buka_files_name = [ f for f in os.listdir(input_dir) if f.endswith('.buka') ]
    for buka_fn in buka_files_name:
        image_dir_path = os.path.join(output_dir,buka_fn.replace('.buka', ''))
        if not os.path.exists(image_dir_path):
            os.mkdir(image_dir_path)
        refine(os.path.join(input_dir,buka_fn), image_dir_path)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(USAGE)
    else:
        print time.strftime('%H:%M:%S')
        extract_dir(sys.argv[1], sys.argv[2])
        print time.strftime('%H:%M:%S')
