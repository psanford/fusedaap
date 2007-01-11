#!/usr/bin/env python
"""
	Fusedaap is a read-only FUSE filesystem that allows for browsing and 
	accessing DAAP (iTunes) music shares.
	
	Copyright 2006, Peter Sanford
	
	This file is part of fusedaap.

    Fusedaap is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    Fusedaap is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with fusedaap; if not, write to the Free Software
    Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

"""


__author__ = "Peter Sanford"
__email__ = "peter dot sanford at wheaton dot edu"
__version__ = "0.2.1"

import os, stat, errno, sys, socket, time, signal
import fuse
import threading
import logging
import daap
import Zeroconf

if not hasattr(fuse, '__version__'):
	raise RuntimeError, \
		"your fuse-py doesn't know of fuse.__version__, probably it's too old."

daapZConfType = "_daap._tcp.local."
daapPort = 3689

#logging set using -d flag
logger = logging.getLogger('fusedaap')

def enableLogging():
	hdlr = logging.FileHandler('fd.log')
	formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	hdlr.setFormatter(formatter)
	logger.addHandler(hdlr)
	logger.setLevel(logging.DEBUG)



class Inode(fuse.Stat):
	"""Stores basic information about a file."""
	def __init__(self, name, permissions):
		"""Populates the values of name and st_mode."""
		self.name = name
		self.st_mode = permissions
		self.st_ino = 0
		self.st_dev = 0
		self.st_nlink = 1
		self.st_uid = int(os.getuid())
		self.st_gid = int(os.getgid())
		now = int(time.time())
		self.st_atime = now
		self.st_mtime = now
		self.st_ctime = now
		self.st_size = 0


class DirInode(Inode):
	"""Represents a directory in the filesystem."""
	def __init__(self, name, permissions=stat.S_IFDIR | 0555):
		Inode.__init__(self, name, permissions)
		self.children = {}
	def addChild(self, inode):
		"""Adds Inode to this directory."""
		self.children[inode.name] = inode
	def removeChild(self, name):
		"""Removes Inode from this directory."""
		del self.children[name]


class SongInode(Inode):
	"""Represents a song file in the file system."""
	def __init__(self, name, filesize, song=None, \
		permissions=stat.S_IFREG | 0444):
		Inode.__init__(self, name, permissions)
		self.st_size = filesize
		self.song = song


class ServiceResolver(threading.Thread):
	"""A class to wrap the Zeroconf.getServiceInfo() method into a thread.
	If the service resolves, will call addHost() method in listener."""
	
	threadCounter = 0
	
	def __init__(self, zeroconf, serviceInfo, listener, timeout):
		threading.Thread.__init__(self)
		self.zeroconf = zeroconf
		self.info = serviceInfo
		self.timeout = timeout
		self.listener = listener
		self.__class__.threadCounter += 1
		logger.info("Total number of ServiceResolver threads created %d"
			% self.__class__.threadCounter)
		self.start()

	def run(self):
		if self.info.request(self.zeroconf, self.timeout):
			logger.info("Found service, setting call back")
			self.listener.addHost(self.info.name, self.info.address)
		else:
			logger.info("Service discovery failed for %s"%self.info.name)
		

class DaapFS(fuse.Fuse):
	def __init__(self, *args, **kw):
		fuse.Fuse.__init__(self, *args, **kw)
		self.dirSup = DirSupervisor()
	
	def getattr(self, path):
		inode = self.dirSup.fetchInode(path)
		if inode is None:
			logger.info("could not find inode: %s"%path)
			return -errno.ENOENT
		return inode

	def readdir(self, path, offset):
		directory = self.dirSup.fetchInode(path)
		if directory == None:
			directory = {} # ls will still work even after host has disconnected
		for r in ['.', '..'] +  directory.children.keys():
			logger.info("readdir: %s"%r)
			if r is ' ' or r is '' or r is None:
				logger.info("ERR readdir: read filename error: '%s'"%r)
				pass
			else:
				yield fuse.Direntry(r.encode(sys.getdefaultencoding(), "ignore"))

	def open(self, path, flags):
		inode = self.dirSup.fetchInode(path)
		if inode is None: 
			return -errno.ENOENT
		accmode = os.O_RDONLY | os.O_WRONLY | os.O_RDWR
		if (flags & accmode) != os.O_RDONLY:
			return -errno.EACCES
	
	def read(self, path, size, offset):
		inode = self.dirSup.fetchInode(path)
		if inode is None:
			return -errno.ENOENT
		name = inode.name
		slen = inode.st_size
		song = inode.song

		if offset < slen:
			if offset + size > slen:
				size = slen - offset
			req = song.requestRange(offset, size)
			buf = req.read(size)
		else:
			buf = ''
		return buf



class HostManager(object):
	"""
	This class manages zeroconf hosts.
	"""
	def __init__(self):
		self.__closed = False #if true, don't connect to any new hosts
		self.listeners = []
		self.allHosts = []
		self.connectedSessions = {} # name -> DAAPSession, use to dissconnect
	
	
	def addHandler(self, listener):
		"""Adds a handler that will be called on the following events:
		
		newHost(host, songs): a new hostname with a list of track objects
		delHost(host): the host has disconnected
		"""
		self.listeners.append(listener)

	
	def addHost(self, name, addr):
		"""Trys to connect to daap server. If able to connect, get song
		listing.
		"""
		if self.__closed:
			return # do not add host if closed
		stripName = _cleanStripName(name)
		address = str(socket.inet_ntoa(addr))
		port = daapPort
		client = AdvancedDAAPClient()
		tracks = []
		try:
			client.connect (address, port)
			session = client.login() 
			database = session.library()
			tracks = database.tracks()
		except Exception, e:
			logger.info("Could not connect to %s: %s"%(stripName, e))
		if len(tracks) > 0:
			logger.info("!!!\n!!! :) !!! Connected to %s\n!!!"%stripName)
			self.connectedSessions[name] = session
			for listener in self.listeners:
				listener.newHost(stripName, tracks)
		else:
			try:
				session.logout() #make sure we don't keep an open connection
			except:
				pass
			logger.info("failed to get find any tracks from %s"%stripName)
			
		
	def addService(self, zeroconf, type, name):
		"""Listener method called when new zeroconf service is detected."""
		if self.__closed:
			return #do NOT add service if closed
		self.allHosts.append(name)
		ServiceResolver(zeroconf, Zeroconf.ServiceInfo(type, name), self, 3000)
		
	def removeService(self, zeroconf, type, name):
		"""Listener method called when zeroconf service disconnects."""
		stripName = _cleanStripName(name)
		stripName = _cleanStripName(name)
		if self.connectedSessions.has_key(name):
			try: 
				self.connectedSessesions[name].logout()
			except:
				pass
			del self.connectedSessions[name]
			self.allHosts.remove(name)
			for listener in self.listeners:
				listener.delHost(stripName)
		else:
			try:
				self.allHosts.remove(name)
			except ValueError:
				logger.info("value error ex. in HM.removeService for %s"%name)
		logger.info("Service %s disconneted"%stripName)

	def closeAllConnections(self):
		"""Closes all open DAAPSession connections."""
		self.__closed = True
		for name, session in self.connectedSessions.items():
			try:
				session.logout()
			except:
				pass
		self.connectedSessions.clear()


class AdvancedDAAPTrack(daap.DAAPTrack):
	"""An extension of daap.DAAPClient with added method 'requestRange'
	which allows for requesting a partial file."""
	def __init__(self, database, atom):
		daap.DAAPTrack.__init__(self, database, atom)
	
	def requestRange(self, offset, length):
		"""Performs a request for a byte range of the file instead of the entire file.
		"""
        # gotta bump this every track download
		self.database.session.connection.request_id += 1
		
		return self.database.session.connection._getResponseWithHeaders(
			self.database.session.connection, "/databases/%s/items/%s.%s"% \
			(self.database.id, self.id, self.type),
			{'session-id':self.database.session.sessionid}, gzip = 0,
			headers = {'Range' : 'bytes=%d-%d'%(offset, offset+length-1)})


	

class AdvancedDAAPClient(daap.DAAPClient):
	"""An extension of daap.DAAPClient with added method getResponse with headers that allows passing other headers to the daap server."""
	def __init__(self):
		daap.DAAPClient.__init__(self)


	def _getResponseWithHeaders(self, daapclient, r, params = {}, gzip = 1, 
			headers={}):
		"""
		Like daap.DAAPClient._get_response() but with the ability to add other http headers.
		"""
		if params:
			l = ['%s=%s' % (k, v) for k, v in params.iteritems()]
			r = '%s?%s' % (r, '&'.join(l))
		hdrs = {
			'Client-DAAP-Version': '3.0',
			'Client-DAAP-Access-Index': '2',
		}
		headers.update(hdrs)
		if gzip: headers['Accept-encoding'] = 'gzip'
		if daapclient.request_id > 0:
			headers[ 'Client-DAAP-Request-ID' ] = daapclient.request_id
		if (daapclient._old_itunes):
			headers[ 'Client-DAAP-Validation' ] = daap.hash_v2(r, 2)
		else:
			headers[ 'Client-DAAP-Validation' ] = daap.hash_v3(r, 2, \
				daapclient.request_id)
		# there are servers that don't allow >1 download from a single HTTP
		# session, or something. Reset the connection each time. Thanks to
		# Fernando Herrera for this one.
		daapclient.socket.close()
		daapclient.socket.connect()
		try:
			daapclient.socket.request('GET', r, None, headers)
		except CannotSendRequest, e:
			logger.error("Error sending request : %s"%e);
		response    = daapclient.socket.getresponse()
		return response
	


class DirSupervisor(object):
	"""
	This class manages the internal file tree for fusedaap. 
	
	The primary role of this class is to control the creation of 
	LocalDirManager objects. 

	DirSupervisor also supports fetching Inodes.
	"""
	def __init__(self):
		self.__fsRoot = DirInode("/")
		self.__fsRoot.st_nlink = 2 #should this be 1?

	def requestDirLease(self, path):
		"""Returns a LocalDirmanager if sucessful, 
		otherwise throws an exception.
		"""
		localName = path.strip('/').split('/').pop()
		if path == "/":
			raise Exception("Cannot lease out root dir.")
		elif len(path.strip("/").split("/")) != 1:
			raise Exception("Only first level leases are valid.")
		elif self.__fsRoot.children.has_key(localName):
			raise Exception("This directory is already leased out.")
		else:
			localRoot = DirInode(localName)
			self.__fsRoot.addChild(localRoot)
			return LocalDirManager(localRoot)
	
	def fetchInode(self, path):
		"""Returns the Inode for the given path, or None if not found."""
		if path == '/':
			return self.__fsRoot
		curdir = self.__fsRoot
		folders = path.strip('/').split('/')
		try:
			for f in folders:
				curdir = curdir.children[f]
			return curdir
		except:
			return None



class LocalDirManager(object):
	def __init__(self, localDirRoot):
		self.__fsRoot = localDirRoot

	def fetchInode(self, path):
		"""Returns the Inode for the given path, or None if not found.
		
		The path variable is the local path, i.e. '/' is the local root folder,
		not the global root.
		"""
		if path == '/':
			return self.__fsRoot
		curdir = self.__fsRoot
		folders = path.strip('/').split('/')
		try:
			for f in folders:
				curdir = curdir.children[f]
			return curdir
		except:
			return None

	def mkDir(self, path):
		"""Creates a directory with the path given and returns the DirInode.
		
			If a node already exits in dir structure, will throw
			an OSError.

		The path variable is the local path, i.e. '/' is the local root folder,
		not the global root.
		"""
		curdir = self.__fsRoot
		folders = path.strip('/').split('/')
		for f in folders:
			if curdir.children.has_key(f):
				curdir = curdir.children[f]
				if not isinstance(curdir, DirInode):
					e = OSError("File %s is not a directory" % curdir)
					e.errno = errno.ENOENT
					raise e
			else:
				newdir = DirInode(f)
				curdir.addChild(newdir)
				curdir = newdir
		return curdir
	
	
	def rmInode(self, path):
		"""Removes the Inode if it exists.

		The path variable is the local path, i.e. '/' is the local root folder,
		not the global root.
		"""
		if path == '/':
			e = OSError("Cannot remove / (root) directory.")
			e.errno = errno.ENOENT
			raise e
		curdir = self.__fsRoot
		folders = path.strip('/').split('/')
		inodeToDel = folders.pop()
		try:
			for f in folders:
				curdir = curdir.children[f]
			curdir.removeChild(inodeToDel)
		except:
			return None

	def rrmInode(self, path, rootNode=None):
		"""
		Like rmInode, but this will also remove any parent folders 
		that become empty after the rm.

		rootNode - dirNode in tree to start descending from, the 
			path needs to only include items below this folder and no '/'
			If no rootNode is supplied, will assume that path is a full path

		will return 1 if everything below has been removed, 0 if 
		there was something that was not removed


		The path variable is the local path, i.e. '/' is the local root folder,
		not the global root.
		"""

		folders = path.strip('/').split('/')
		if rootNode == None:
			if path == '/':
				e = OSError("Cannot remove / (root) directory.")
				e.errno = errno.ENOENT
				raise e
			curdir = self.__fsRoot
			nextFolder = folders.pop(0)
			self.rrmInode(path, curdir)
		else:
			curdir = rootNode
			if len(folders) == 1 and folders[0] == '':
				return True
			else:
				nextFolder = folders.pop(0)
				if self.rrmInode('/'.join(folders), 
				curdir.children[nextFolder]):
					curdir.removeChild(nextFolder)
					if len(curdir.children) == 0:
						return True
					else:
						return False
				else:
					return False

class HostDirHandler(object):
	"""Manages files under /hosts dir."""
	def __init__(self, directoryManager):
		self.dirMan = directoryManager

	def newHost(self, host, songs):
		for song in songs: 
			fileName = "%s-%s-%s.%s" % \
				(song.artist, song.album, song.name, song.type)
			fileName = _getCleanName(fileName)
			putDir = self.dirMan.mkDir("/%s/%s/%s"% \
				(host, _getCleanName(song.artist),
					_getCleanName(song.album)))
			if not putDir.children.has_key(fileName):
				songNode = SongInode(fileName, song.size, song=song)
				putDir.addChild(songNode)
				logger.info("Add %s/%s/%s"%(host, putDir.name, songNode.name))
	def delHost(self, host):
		self.dirMan.rrmInode("/%s"%host)



class ArtistDirHandler(object):
	"""Manages files under /artists dir.
	
	Under directory structure is 
		/artists/[artist_name]/[album_name]/[track](-host).[mp3|m4a]

		If more than one host is sharing a song, then one of them will 
		contain -host to seperate the two.
	"""
	def __init__(self, directoryManager):
		self.hosts = {}
		self.dirMan = directoryManager

	def newHost(self, host, songs):
		sngList = []
		for song in songs: 
			fileName = "%s.%s"%(song.name, song.type)
			fileName = _getCleanName(fileName)
			directory = "/%s/%s"% \
				(_getCleanName(song.artist), _getCleanName(song.album))
			putDir = self.dirMan.mkDir(directory)
			if not putDir.children.has_key(fileName):
				if not isinstance(song, AdvancedDAAPTrack): 
					#make sure song is an AdvancedDAAPTrack
					song = AdvancedDAAPTrack(song.database, song.atom) 
				songNode = SongInode(fileName, song.size, song=song)
				putDir.addChild(songNode)
				logger.info("art: Add %s/%s/%s"%\
					(host, putDir.name, songNode.name))
				sngList.append("%s/%s"%(directory, fileName))
			else:
				#song already here by other host 
				fileName = "%s-%s.%s"%(host, song.name, song.type)
				fileName = _getCleanName(fileName)
				if not putDir.children.has_key(fileName):
					songNode = SongInode(fileName, song.size, song=song)
					putDir.addChild(songNode)
					logger.info("Add %s/%s/%s"%\
						(host, putDir.name, songNode.name))
					sngList.append("%s/%s"%(directory, fileName))
		self.hosts[host] = sngList

	def delHost(self, host):
		if host in self.hosts:
			sngList = self.hosts[host] # all songs for host
			map(self.dirMan.rrmInode, sngList)


		
def _cleanStripName(name):
	"""Returns a filesystem friendly name for a host."""
	cleanName = _getCleanName(name)
	return cleanName[:cleanName.index('.'+daapZConfType)]
	
def _getCleanName(name):
	"""Returns a filesystem friendly string.
	
	Replace the following ' ', ':', '<', '>', '|', '?',
	'\\', '@', '/'
	"""
	if name is None:
		return 'none'
	return name.encode(sys.getdefaultencoding(), "ignore").strip()\
		.replace(' ', '_').replace(':', '_').replace('<', '_')\
		.replace('>', '_').replace('|', '_').replace('?', '_')\
		.replace('\\', '_').replace('@', '_').replace('/', '_')


def main():
	usage = """Fusedaap :""" + fuse.Fuse.fusage
	server = DaapFS()
	server.fuse_args.setmod('foreground')
	server.parse(errex=1)
	server.multithreaded = True
	hostMan = HostManager()
	hdh = HostDirHandler(server.dirSup.requestDirLease("/hosts"))
	hostMan.addHandler(hdh)
	adh = ArtistDirHandler(server.dirSup.requestDirLease("/artists"))
	hostMan.addHandler(adh)
	r = Zeroconf.Zeroconf()
	r.addServiceListener(daapZConfType, hostMan)
	try:
		server.main() # main loop
	except:
		print 'Exiting . . .'
		r.close()
		return
	logger.info("closing zeroconf in main")
	print "Disconnecting from services . . ."
	r.close() # close zeroconf first so no new servers are connected to
	hostMan.closeAllConnections() 
	


if __name__ == '__main__':
	debugArgs = filter(lambda x: x == '-d', sys.argv)
	if len(debugArgs):
		enableLogging()
	logger.info("=========START APP==========")
	try:
		main()
	except Exception, e:
		logger.error("!Caught Exception %s"%e)
		raise
	logger.info("=========END APP==========")

