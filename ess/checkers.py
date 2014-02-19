"""
Module that provides a SSH public key checker, but without depending
necessarily on pwd
"""
try:
    import pwd as _pwd
except ImportError:
    _pwd = None

from zope.interface import implementer, Interface

from twisted.conch import error
from twisted.conch.ssh.keys import Key
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import ISSHPrivateKey
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer
from twisted.python import log
from twisted.python.util import runAsEffectiveUser
from twisted.python.filepath import FilePath


class ISSHPublicKeyDB(Interface):
    """
    An object that provides valid authorized ssh keys mapped to usernames
    """
    def getAuthorizedKeys(username):
        """
        @param username: C{str} username of the user

        @return: an iterable of L{twisted.conch.ssh.keys.Key}
        """

def readAuthorizedKeyFile(fileobj):
    """
    Reads keys from an authorized keys file

    @param fileobj: an open file object which can be read from

    @return: an iterable of L{twisted.conch.ssh.keys.Key}
    """
    for line in fileobj:
        line = line.strip()
        if not line.startswith('#'):  # for comments
            try:
                yield Key.fromString(line)
            except:
                pass


@implementer(ISSHPublicKeyDB)
class AuthorizedKeysFilesMapping(object):
    """
    Object that provides SSH public keys based on a dictionary of usernames
    mapped to authorized key files

    @ivar mapping: C{dict} of usernames mapped to iterables of authorized key
        files
    """
    def __init__(self, mapping):
        self.mapping = mapping

    def getAuthorizedKeys(self, username):
        """
        @see: L{ess.checkers.ISSHPublicKeyDB}
        """
        for fp in (FilePath(f) for f in self.mapping.get(username, [])):
            if fp.exists():
                try:
                    f = fp.open()
                except:
                    log.msg("Unable to read {0}".format(fp.path))

                for key in readAuthorizedKeyFile(f):
                    yield key


@implementer(ISSHPublicKeyDB)
class UNIXAuthorizedKeysFiles(object):
    """
    Object that provides SSH public keys based on public keys listed in
    authorized_keys and authorized_keys2 files in UNIX user .ssh/ directories.

    @ivar pwd: access to the Unix user account and password database (default
        is the Python module L{pwd})
    """
    def __init__(self, pwd=None):
        self.pwd = pwd
        if pwd is None:
            self.pwd = _pwd

    def getAuthorizedKeys(self, username):
        """
        @see: L{ess.checkers.ISSHPublicKeyDB}
        """
        passwd = self.pwd.getpwnam(username)

        root = FilePath(passwd.pw_dir).child('.ssh')
        files = ['authorized_keys', 'authorized_keys2']
        for fp in (root.child(f) for f in files):
            if fp.exists():
                try:
                    f = fp.open()
                except IOError:
                    f = runAsEffectiveUser(passwd.pw_uid, passwd.pw_gid,
                                           fp.open)

                for key in readAuthorizedKeyFile(f):
                    yield key


@implementer(ICredentialsChecker)
class SSHPublicKeyChecker(object):
    """
    Checker that authenticates SSH public keys, based on public keys listed in
    authorized_keys and authorized_keys2 files in user .ssh/ directories.

    Providing this checker with a L{UNIXAuthorizedKeysFiles} should be
    equivalent to L{twisted.conch.checkers.SSHPublicKeyDatabase}.

    @param keydb: a provider of L{ISSHPublicKeyDB}
    """
    credentialInterfaces = (ISSHPrivateKey,)

    def __init__(self, keydb):
        self.keydb = keydb

    def requestAvatarId(self, credentials):
        d = defer.maybeDeferred(self._sanityCheckKey, credentials)
        d.addCallback(self._checkKey, credentials)
        d.addCallback(self._verifyKey, credentials)
        return d

    def _sanityCheckKey(self, credentials):
        """
        Check whether the provided credentials are a valid SSH key with a
        signature (does not actually verify the signature)

        @param credentials: The credentials offered by the user.
        @type credentials: L{ISSHPrivateKey} provider

        @raise ValidPublicKey: the credentials do not include a signature. See
            L{error.ValidPublicKey} for more information.

        @raise BadKeyError: the key included with the credentials is not
            recognized as a key

        @return: L{twisted.conch.ssh.keys.Key} of the key in the credentials
        """
        if not credentials.signature:
            raise error.ValidPublicKey()

        return Key.fromString(credentials.blob)

    def _checkKey(self, pubKey, credentials):
        """
        Check the public key against all authorized keys (if any) for the
        user.

        @param pubKey: L{twisted.conch.ssh.keys.Key} of the key in the
            credentials (just to prevent it from having to be calculated
            again)

        @param credentials: The credentials offered by the user.
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: if the key is not authorized, or if there
            was any error obtaining a list of authorized keys for the user

        @return: The C{pubKey}, if the key is authorized
        """
        try:
            if any(key == pubKey for key in
                   self.keydb.getAuthorizedKeys(credentials.username)):
                return pubKey
        except:
            log.err()
            raise UnauthorizedLogin("Unable to get avatar id")

        raise UnauthorizedLogin("Key not authorized")

    def _verifyKey(self, pubKey, credentials):
        """
        Check whether the credentials themselves are valid, now that we know
        if the key matches the user.

        @param pubKey: L{twisted.conch.ssh.keys.Key} of the key in the
            credentials (just to prevent it from having to be calculated
            again)

        @param credentials: The credentials offered by the user.
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: if the key signature is invalid or there
            was any error verifying the signature

        @return: The user's username, if authentication was successful.
        """
        try:
            if pubKey.verify(credentials.signature, credentials.sigData):
                return credentials.username
        except:  # any error should be treated as a failed login
            log.err()
            raise UnauthorizedLogin('Error while verifying key')

        raise UnauthorizedLogin("Key signature invalid.")
