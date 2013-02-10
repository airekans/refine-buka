import re
import struct
import os
import sys
import time

def refine(file_name,output_dir):
    if not os.path.isdir(output_dir):
        print(USAGE)
        raise IOError('output dir `%s` not found' %output_dir)
    with open(file_name) as f:
        buff = f.read(10000)
        toc = re.findall(r'\x00([\x00-\xff]{8})c(\d{4}\.jpg)',buff)
        for index in toc:
            pos, size = struct.unpack('<II', index[0])
            img = open(os.path.join(output_dir,index[1]),'wb')
            f.seek(pos)
            data =  f.read(size)
            img.write(data)
            img.close()

USAGE = """
    python refine.py FILE_NAME OUTPUT_DIR
"""

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(USAGE)
    else:
        print time.strftime('%H:%M:%S')
        refine(sys.argv[1], sys.argv[2])
        print time.strftime('%H:%M:%S')




