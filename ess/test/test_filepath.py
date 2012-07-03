"""
Tests for the overriden FilePath class
"""
import os
from twisted.test import test_paths

from ess import filepath


class TestFilePath(test_paths.FilePathTestCase):

    def setUpLinks(self):
        test_paths.FilePathTestCase.setUp(self)
        os.symlink(self.path.child("sub1").path, self._mkpath("sub1.link"))
        os.symlink(self.path.child("sub1").child("file2").path,
                   self._mkpath("file2.link"))
        self.all.sort()

    def test_openWithModeAndFlags(self):
        """
        Verify that passing both modes and flags will raise an error
        """
        self.path = filepath.FilePath(self.path.path)
        self.assertRaises(ValueError, self.path.child('file1').open,
                          mode='w+', flags=os.O_RDWR)

    def test_openWithFlags_Nonexisting(self):
        """
        Verify that nonexistant file opened without the create flag will fail
        """
        self.path = filepath.FilePath(self.path.path)
        created = self.path.child('createdFile')
        self.assertRaises((OSError, IOError), created.open, flags=os.O_RDWR)

    def test_openWithFlags_NoFlags(self):
        """
        Verify that file opened with no read/write flags will default to
        reading
        """
        self.path = filepath.FilePath(self.path.path)
        created = self.path.child('createdFile')
        f = created.open(flags=os.O_CREAT)
        self.failUnless(created.exists())
        self.assertEquals(f.read(), '')
        f.close()

    def test_openWithFlags_CannotRead(self):
        """
        Verify that file opened write only will not be readable.
        """
        self.path = filepath.FilePath(self.path.path)
        f = self.path.child("file1").open(flags=os.O_WRONLY)
        f.write('writeonly')
        self.assertRaises((OSError, IOError), f.read)
        f.close()

    def test_openWithFlags_CannotWrite(self):
        """
        Verify that file opened with no write can be read from but not
        written to
        """
        self.path = filepath.FilePath(self.path.path)
        f = self.path.child("file1").open(flags=os.O_APPEND)
        self.assertEquals(f.read(), 'file 1')
        self.assertRaises((OSError, IOError), f.write, "append")
        f.close()

    def test_openWithFlags_AppendWrite(self):
        """
        Verify that file opened with the append flag and the writeonly
        flag can be appended to but not overwritten, and not read from
        """
        self.path = filepath.FilePath(self.path.path)
        f = self.path.child("file1").open(flags=os.O_WRONLY | os.O_APPEND)
        self.assertRaises((OSError, IOError), f.read)
        f.write('append')
        f.seek(0)
        f.write('append2')
        f.close()
        f = self.path.child("file1").open()
        self.assertEquals(f.read(), self.f1content + 'appendappend2')
        f.close()

    def test_openWithFlags_AppendRead(self):
        """
        Verify that file opened with readwrite and append is both appendable
        to and readable from
        """
        self.path = filepath.FilePath(self.path.path)
        f = self.path.child("file1").open(flags=os.O_RDWR | os.O_APPEND)
        f.write('append')
        f.seek(0)
        f.write('append2')
        f.seek(0)
        self.assertEquals(f.read(), self.f1content + 'appendappend2')
        f.close()

    def test_openWithFlags_ReadWrite_NoTruncate(self):
        """
        Verify that file opened readwrite is both readable and writable.
        """
        self.path = filepath.FilePath(self.path.path)
        created = self.subfile("createdFile")
        created.write("0000000000000000")
        created.close()
        created = self.path.child("createdFile")
        f = created.open(flags=os.O_RDWR)
        f.write('readwrite')
        f.seek(0)
        self.assertEquals(f.read(), 'readwrite0000000')
        f.close()

    def test_openWithFlags_Truncate(self):
        """
        Verify that file called with truncate will be overwritten
        """
        self.path = filepath.FilePath(self.path.path)
        f = self.path.child("file1").open(flags=os.O_RDWR | os.O_TRUNC)
        f.write('overwrite')
        f.seek(0)
        self.assertEquals(f.read(), 'overwrite')
        f.close()

    def test_openWithFlags_Exclusive(self):
        """
        Verify that file opened with the exclusive flag will raise an error
        """
        self.path = filepath.FilePath(self.path.path)
        self.assertRaises((OSError, IOError), self.path.child("file1").open,
                          flags=(os.O_RDWR | os.O_CREAT | os.O_EXCL))

    def test_walk(self):  # isn't a replacement exactly
        self.setUpLinks()
        self.path = filepath.FilePath(self.path.path)
        test_paths.FilePathTestCase.test_walk(self)

    def testRealpath(self):
        """
        Verify that a symlink is correctly normalized
        """
        self.setUpLinks()
        self.path = filepath.FilePath(self.path.path)
        self.assertEquals(self.path.child("sub1.link").realpath(),
                          self.path.child("sub1"))
        self.assertEquals(self.path.child("sub1").realpath(),
                          self.path.child("sub1"))

    def testStatCache(self):
        self.setUpLinks()
        self.path = filepath.FilePath(self.path.path)
        test_paths.FilePathTestCase.testStatCache(self)
        sub = self.path.child("sub1")
        sublink = self.path.child("sub1.link")
        sub.restat()
        sublink.restat(followLink=False)
        self.assertNotEquals(sub.statinfo, sublink.statinfo)
        sublink.restat()
        self.assertEquals(sub.statinfo, sublink.statinfo)
        sub.restat(followLink=False)
        self.assertEquals(sub.statinfo, sublink.statinfo)
