"""
Module that provides a SSH public key checker, but without depending
necessarily on pwd
"""
import base64, binascii

try:
    import pwd as _pwd
except ImportError:
    _pwd = None

from zope.interface import implementer, Interface

from twisted.conch import error
from twisted.conch.ssh import keys
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

        @return: an iterable which returns a series of binary strings
            representing authorized keys
        """

def readAuthorizedKeyFile(fileobj):
    """
    Reads keys from an authorized keys file

    @param fileobj: an open file object which can be read from

    @return: an iterable of strings representing base64-decoded authorized
        keys contained in the authorized keys file
    """
    for line in fileobj:
        tokenized = line.strip().split()
        if len(tokenized) >= 2:
            try:
                yield base64.decodestring(tokenized[1])
            except binascii.Error:
                pass


@implementer(ISSHPublicKeyDB)
class AuthorizedKeysFilesDB(object):
    """
    """


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
        d = defer.maybeDeferred(self._checkKey, credentials)
        d.addErrback(self._translateErrors)
        d.addCallback(self._cbRequestAvatarId, credentials)
        return d

    def _cbRequestAvatarId(self, validKey, credentials):
        """
        Check whether the credentials themselves are valid, now that we know
        if the key matches the user.

        @param validKey: A boolean indicating whether or not the public key
            matches a key in the user's authorized_keys file.

        @param credentials: The credentials offered by the user.
        @type credentials: L{ISSHPrivateKey} provider

        @raise UnauthorizedLogin: (as a failure) if the key does not match the
            user in C{credentials}. Also raised if the user provides an invalid
            signature.

        @raise ValidPublicKey: (as a failure) if the key matches the user but
            the credentials do not include a signature. See
            L{error.ValidPublicKey} for more information.

        @return: The user's username, if authentication was successful.
        """
        if not validKey:
            raise UnauthorizedLogin("invalid key")
        if not credentials.signature:
            raise error.ValidPublicKey()
        else:
            try:
                pubKey = keys.Key.fromString(credentials.blob)
                if pubKey.verify(credentials.signature, credentials.sigData):
                    return credentials.username
            except: # any error should be treated as a failed login
                log.err()
                raise UnauthorizedLogin('error while verifying key')
        raise UnauthorizedLogin("unable to verify key")


    def _checkKey(self, credentials):
        """
        Checks the user credentials against all authorized keys (if any) for
        the user.
        """
        return any(key == credentials.blob for key in
                   self.keydb.getAuthorizedKeys(credentials.username))

    def _translateErrors(self, f):
        """
        Translates all errors into L{UnauthorizedLogin} errors.
        """
        log.msg(f)
        raise UnauthorizedLogin("unable to get avatar id")
