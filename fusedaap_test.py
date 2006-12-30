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

import fusedaap
import unittest


class Test_getCleanName(unittest.TestCase):
	knownInput = ( ('test', 'test'),
					('?ef?', '_ef_'),
					('te\\st', 'te_st'),
					('te st', 'te_st'),
					('test:', 'test_'),
					('ab|cd', 'ab_cd'),
					('abcd@@', 'abcd__'),
					('@<?>|', '_____'),
					('TE>st', 'TE_st'))
	def test_getCleanNameKnownInput(self):
		"""_getCleanName should give known results for known input."""
		for dirty, clean in self.knownInput:
			out = fusedaap._getCleanName(dirty)
			self.assertEqual(clean, out)

class Test_cleanStripName(unittest.TestCase):
	daapZConfType = "_daap._tcp.local."
	knownInput = (('cool music._daap._tcp.local.', 'cool_music'),
					("whos in the house? ._daap._tcp.local.", 
					"whos_in_the_house__"))

	def test_cleanStripNameKnownInput(self):
		"""_cleanStripName should return a known result for known input."""
		for raw, clean in self.knownInput:
			out = fusedaap._cleanStripName(raw)
			self.assertEqual(clean, out)
	
	def test_cleanStripNameBadInput(self):
		"""_cleanStripName should raise a ValueError if the daap zeroconf ext
		is not present."""
		self.assertRaises(ValueError, fusedaap._cleanStripName, "no daap ext.")
	

class Test_LocalDirManager_fetchInode(unittest.TestCase):
	
	def setUp(self):
		self.dirLocalMan = fusedaap.LocalDirManager(fusedaap.DirInode('testDir'))
		self.dirLocalMan.fsRoot = self.dirLocalMan.fetchInode('/')#bc __fsRoot is private
		self.firstLevel = ( 'dir1', 'dir2', 'dir3')
		self.secondLevel1 = ( 'dir1a' , 'dir1b')
		self.secondLevel2 = ( 'dir2a',)
		self.thirdLevel1a = ( 'songFile1', 'songFile2')

		self.dirPaths = ('/dir1', '/dir2', '/dir1/dir1a', '/dir1/dir1b',
					'/dir2/dir2a', '/dir2/dir2a')

		self.songPaths = ('/dir1/dir1a/songFile1', '/dir1/dir1a/songFile2')

		for f in self.firstLevel:
			self.dirLocalMan.fsRoot.addChild(fusedaap.DirInode(f))
		for f in self.secondLevel1:
			self.dirLocalMan.fsRoot.children['dir1'].addChild(fusedaap.DirInode(f))
		for f in self.secondLevel2:
			self.dirLocalMan.fsRoot.children['dir2'].addChild(fusedaap.DirInode(f))
		for s in self.thirdLevel1a:
			self.dirLocalMan.fsRoot.children['dir1'].children['dir1a'].addChild(fusedaap.SongInode(s, 5))


	def tearDown(self):
		self.dirLocalMan = None

	def test_fetchInodeGoodInput(self):
		""""LocalDirManager.fetchInode should return inodes that exist in tree."""
		for dir in self.dirPaths:
			node = self.dirLocalMan.fetchInode(dir)
			self.assertTrue(isinstance(node, fusedaap.DirInode))
			self.assertTrue(dir.endswith(node.name))
		for s in self.songPaths:
			node = self.dirLocalMan.fetchInode(s)
			self.assertTrue(isinstance(node, fusedaap.SongInode))
			self.assertTrue(s.endswith(node.name))

	def test_fetchInodeMissingNode(self):
		"""LocalDirManager.fetchInode should return None if inode does not exist."""
		self.dirLocalMan = fusedaap.LocalDirManager(fusedaap.DirInode('testDir'))
		for f in self.dirPaths[1:]:
			self.assertEquals(None, self.dirLocalMan.fetchInode(f))
	
	def test_fetchDirNodeWithEndingSlash(self):
		"LocalDirManager.fetchInode should strip ending slashes from the path."""
		for f in self.dirPaths[1:]:
			dir = '%s/'%f
			node = self.dirLocalMan.fetchInode(dir)
			self.assertTrue(isinstance(node, fusedaap.DirInode))
			self.assertTrue(f.endswith(node.name))


class Test_LocalDirManager_mkDir(unittest.TestCase):
	def setUp(self):
		self.dirLocalMan = fusedaap.LocalDirManager(fusedaap.DirInode('testDir'))
		self.songPaths = ('/dir1/dir1a/songFile1', '/dir1/dir1a/songFile2')
		self.dirPaths = ('/dir2', '/dir1/dir1a', '/dir1/dir1b', '/dir1'
					'/dir2/dir2a', '/dir2/dir2a')

	def test_mkDirGoodInput(self):
		"""LocalDirManager.mkDirGoodInput should create known directories with a known
		input."""
		map(self.dirLocalMan.mkDir, self.dirPaths)
		for f in self.dirPaths:
			node = self.dirLocalMan.fetchInode(f)
			self.assertTrue(isinstance(node, fusedaap.DirInode))
			self.assertTrue(f.endswith(node.name))

	def test_mkDirOverSongNode(self):
		"""LocalDirManager.mkDir should throw an exception if it tries to create a folder where a filenode (SongNode) exists."""
		rootNode = self.dirLocalMan.fetchInode('/')
		rootNode.addChild(fusedaap.SongInode("song", 1234))
		self.assertRaises(Exception, self.dirLocalMan.mkDir, "song")
		self.assertTrue(isinstance(self.dirLocalMan.fetchInode('/song'), 
			fusedaap.SongInode))

class Test_LocalDirManager_rmInode(unittest.TestCase):
	def setUp(self):
		self.dirLocalMan = fusedaap.LocalDirManager(fusedaap.DirInode('testDir'))
		self.songPaths = ('/dir1/dir1a/songFile1', '/dir1/dir1a/songFile2')
		self.dirPaths = ('/dir2', '/dir1/dir1a', '/dir1/dir1b', '/dir1'
					'/dir2/dir2a', '/dir2/dir2a')

	def test_rmInodeGoodInput(self):
		"""LocalDirManager.rmInode should remove inodes that exist."""
		map(self.dirLocalMan.mkDir, self.dirPaths)
		self.dirLocalMan.rmInode('/dir2')
		self.assertEqual(None, self.dirLocalMan.fetchInode('/dir2'))
		self.assertEqual(None, self.dirLocalMan.fetchInode('/dir2/dir2a'))
		self.assertTrue(
			isinstance(self.dirLocalMan.fetchInode('/'), fusedaap.DirInode))
		self.assertTrue(isinstance(self.dirLocalMan.fetchInode('/dir1/dir1a'), 
			fusedaap.DirInode))

	def test_rmInodeRoot(self):
		"""LocalDirManager.rmInode should throw an OSError if you try to remove
		   the '/' node."""
		self.assertRaises(OSError, self.dirLocalMan.rmInode, '/')

	
class Test_LocalDirManager_rrmInode(unittest.TestCase):
	def setUp(self):
		self.dirLocalMan = fusedaap.LocalDirManager(fusedaap.DirInode('testDir'))
		self.dirPaths = ('/dir2', '/dir1/dir1a', '/dir1', 
			'/dir1/dir1a/removeme', '/dir2/dir2a', '/dir2/dir2a')

	def test_rrmInodeGoodInput(self):
		"""LocalDirManager.rrmInode should remove inode and all empty parent dirs."""
		map(self.dirLocalMan.mkDir, self.dirPaths)
		self.dirLocalMan.rrmInode('/dir1/dir1a/removeme')
		self.assertEqual(None, self.dirLocalMan.fetchInode('/dir1/dir1a/removeme'))
		self.assertEqual(None, self.dirLocalMan.fetchInode('/dir1/'))
		self.assertTrue(
			isinstance(self.dirLocalMan.fetchInode('/'), fusedaap.DirInode))

class Test_DirSupervisor_requestDirLease(unittest.TestCase):
	def setUp(self):
		self.dirSup = fusedaap.DirSupervisor()
		self.input = ('/dir1', '/dir2/', '/dirA')
	
	def test_requestDirLeaseGoodInput(self):
		"""DirSupervisor.requestDirLease should return LocalDirManager objects if the directories are not yet controlled. """
		for f in self.input:
			result = self.dirSup.requestDirLease(f)
			self.assertTrue(isinstance(result, fusedaap.LocalDirManager))

	def test_requestDirLeaseSecondRequest(self):
		"""DirSupervisor.requestDirLease should throw an exception if the requested directory is already held."""
		for f in self.input:
			self.dirSup.requestDirLease(f)
		
		for f in self.input:
			self.assertRaises(Exception, self.dirSup.requestDirLease, f)
	
	def test_requestDirLeaseRoot(self):
		"""DirSupervisor.requestDirLease should throw an exception if the requested directory is the root."""
		self.assertRaises(Exception, self.dirSup.requestDirLease, '/')
	
	def test_requestDirLeaseDeep(self):
		"""DirSupervisor.requestDirLease should throw an exception if the requested directory is any deeper than one level in the tree (e.g. /dir1/dirA is not allowed)."""
		self.assertRaises(Exception, self.dirSup.requestDirLease, '/dir1/dirA')
		for f in self.input:
			self.dirSup.requestDirLease(f)
		self.assertRaises(Exception, self.dirSup.requestDirLease, '/dir1/dirA')



class Test_DirSupervisor_fetchInode(unittest.TestCase):
	def setUp(self):
		self.dirSup = fusedaap.DirSupervisor()
		self.input = ('/dir1', '/dir2', '/dirA')
		self.inputL2 = ('/dirA', '/dirB')
		self.managers = map(self.dirSup.requestDirLease, self.input)
		for m in self.managers:
			map(m.mkDir, self.inputL2)

	def test_fetchInode_goodInput(self):
		"""DirSupervisor.fetchInode should return DirInodes for any inodes that exist in the tree."""
		node = self.dirSup.fetchInode('/')
		self.assertTrue(isinstance(node, fusedaap.DirInode))
		self.assertEquals(node.name, '/')
		for f in self.input:
			node = self.dirSup.fetchInode(f)
			self.assertTrue(isinstance(node, fusedaap.DirInode))
			self.assertEquals(node.name, f.strip('/'))
			for l2 in self.inputL2:
				node = self.dirSup.fetchInode(f+l2)
				self.assertTrue(isinstance(node, fusedaap.DirInode))
				self.assertEquals(node.name, l2.strip('/'))
	
	def test_fetchInode_badInput(self):
		"""DirSupervisor.fetchInode should return None for any nodes not found in the tree."""
		node = self.dirSup.fetchInode('/missingDir')
		self.assertEquals(node, None)
		node = self.dirSup.fetchInode('/dir1/missing')
		self.assertEquals(node, None)


		


if __name__ == "__main__":
	unittest.main()
