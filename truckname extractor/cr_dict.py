import os, zipfile
 
rootdir='./'
list = {}

def getExtension(filename):
	return filename.split('.').pop()

def getFirstLine(file):
	return file.readlines()[0].strip()

def getFilename(path):
	return path.split('/').pop()
	
 
for subdir, dirs, files in os.walk(rootdir):
	for file in files:
		ext = getExtension(file)
		
		if ext == "zip":
			try:
				z = zipfile.ZipFile(file)
			except zipfile.BadZipfile:
				continue
			for f in z.namelist():
				ext_zip = getExtension(f)
				if ext_zip in ['truck', 'trailer', 'airplane', 'boat', 'load']:
					list[getFilename(f)] = getFirstLine(z.open(f))
			z.close()
		elif ext in ['truck', 'trailer', 'airplane', 'boat', 'load']:
			f = open(file, 'r')
			list[getFilename(file)] = getFirstLine(f)
			f.close()

output = open('output.txt', 'w')
output.write("list = {\n")
for filename in list:
	output.write("	'%s': '%s',\n" % (filename, list[filename]))
output.write("}")
output.close()