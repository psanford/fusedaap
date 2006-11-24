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
	

class Test_DaapFSfetchInode(unittest.TestCase):
	
	def setUp(self):
		self.dfs = fusedaap.DaapFS()
		self.emptyDir = fusedaap.DirInode('')
		self.emptySong = fusedaap.SongInode('', 5)
		self.firstLevel = ( 'dir1', 'dir2', 'dir3')
		self.secondLevel1 = ( 'dir1a' , 'dir1b')
		self.secondLevel2 = ( 'dir2a',)
		self.thirdLevel1a = ( 'songFile1', 'songFile2')

		self.dirPaths = ('/', '/dir1', '/dir2', '/dir1/dir1a', '/dir1/dir1b',
					'/dir2/dir2a', '/dir2/dir2a')

		self.songPaths = ('/dir1/dir1a/songFile1', '/dir1/dir1a/songFile2')

		for f in self.firstLevel:
			self.dfs.fsRoot.addChild(fusedaap.DirInode(f))
		for f in self.secondLevel1:
			self.dfs.fsRoot.children['dir1'].addChild(fusedaap.DirInode(f))
		for f in self.secondLevel2:
			self.dfs.fsRoot.children['dir2'].addChild(fusedaap.DirInode(f))
		for s in self.thirdLevel1a:
			self.dfs.fsRoot.children['dir1'].children['dir1a'].addChild(fusedaap.SongInode(s, 5))


	def tearDown(self):
		self.dfs = None

	def test_fetchInodeGoodInput(self):
		""""DaapFS.fetchInode should return inodes that exist in tree."""
		for dir in self.dirPaths:
			node = self.dfs.fetchInode(dir)
			self.assertEqual(type(node), type(self.emptyDir))
			self.assertTrue(dir.endswith(node.name))
		for s in self.songPaths:
			node = self.dfs.fetchInode(s)
			self.assertEqual(type(node), type(self.emptySong))
			self.assertTrue(s.endswith(node.name))

	def test_fetchInodeMissingNode(self):
		"""DaapFS.fetchInode should return None if inode does not exist."""
		self.dfs = fusedaap.DaapFS()
		for f in self.dirPaths[1:]:
			self.assertEquals(None, self.dfs.fetchInode(f))
	
	def test_fetchDirNodeWithEndingSlash(self):
		"DaapFS.fetchInode should strip ending slashes from the path."""
		for f in self.dirPaths[1:]:
			dir = '%s/'%f
			node = self.dfs.fetchInode(dir)
			self.assertEquals(type(self.emptyDir), type(node))
			self.assertTrue(f.endswith(node.name))


class Test_DaapFSmkDir(unittest.TestCase):
	def setUp(self):
		self.dfs = fusedaap.DaapFS()
		self.emptyDir = fusedaap.DirInode('')
		self.emptySong = fusedaap.SongInode('', 5)
		self.songPaths = ('/dir1/dir1a/songFile1', '/dir1/dir1a/songFile2')
		self.dirPaths = ('/dir2', '/dir1/dir1a', '/dir1/dir1b', '/dir1'
					'/dir2/dir2a', '/dir2/dir2a')

	def test_mkDirGoodInput(self):
		"""DaapFS.mkDirGoodInput should create known directories with a known
		input."""
		map(self.dfs.mkDir, self.dirPaths)
		for f in self.dirPaths:
			node = self.dfs.fetchInode(f)
			self.assertEqual(type(node), type(self.emptyDir))
			self.assertTrue(f.endswith(node.name))

	def test_mkDirOverSongNode(self):
		"""DaapFS.mkDir should throw an exception if it tries to create a folder where a filenode (SongNode) exists."""
		return false


	def test_mkDirBadInput(self):
		return false





if __name__ == "__main__":
	unittest.main()
