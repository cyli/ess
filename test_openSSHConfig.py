import openSSHConfig
from twisted.trial import unittest
from twisted.python.filepath import FilePath

class TestOpenSSHConfig(unittest.TestCase):

    def setUp(self):
        self.directory = FilePath(self.mktemp())
        self.directory.createDirectory()


    def test_files(self):
        openSSHConfig.setupConfig(self.directory.path, 2222)
        for file in self.directory.children():
            f = file.open()
            contents = f.read()
            f.close()
            self.assertTrue("%" not in contents)
        self.assertEquals(len(self.directory.children()), 5)


    def test_commandOptions(self):
        for option in openSSHConfig.setupConfig(self.directory.path, 2222):
            self.assertTrue("%" not in option)
