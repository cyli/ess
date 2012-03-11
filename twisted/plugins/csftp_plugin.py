from csftp import server

from zope.interface import implements

from twisted.internet import defer
from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker
from twisted.application import internet
from twisted.conch.openssh_compat.factory import OpenSSHFactory
from twisted.conch.manhole_ssh import ConchFactory
from twisted.cred import credentials, checkers, portal, strcred


class AlwaysAllow(object):
    credentialInterfaces = credentials.IUsernamePassword,
    implements(checkers.ICredentialsChecker)

    def requestAvatarId(self, credentials):
        return defer.succeed(credentials.username)



class Options(usage.Options, strcred.AuthOptionMixin):
    synopsis = "[options]"
    longdesc = ("Makes a Chrooted SFTP Server.  If --root is not passed as a "
        "parameter, uses the current working directory.  If no auth service "
        "is specified, it will allow anyone in.")
    optParameters = [
         ["root", "r", './', "Root directory"],
         ["port", "p", "8888", "Port on which to listen"],
         ["keyDirectory", "k", None, "Directory to look for host keys in.  "
            "If this is not provided, fake keys will be used."],
         ["moduli", "", None, "Directory to look for moduli in "
                              "(if different from --keyDirectory)"]
    ]
    compData = usage.Completions(optActions={
            "root": usage.CompleteDirs(descr="root directory"),
            "keyDirectory": usage.CompleteDirs(descr="key directory"),
            "moduli": usage.CompleteDirs(descr="moduli directory")
        })



class CSFTPServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "csftp"
    description = "Chrooted SFTP Server"
    options = Options

    def makeService(self, options):
        """
        Construct a TCPServer from a factory defined in myproject.
        """
        _portal = portal.Portal(
            server.ChrootedSSHRealm(server.FilePath(options['root']).path),
            options.get('credCheckers', [AlwaysAllow()]))

        if options['keyDirectory']:
            print 'what'
            factory = OpenSSHFactory()
            factory.portal = _portal
            factory.dataRoot = options['keyDirectory']
            factory.moduliRoot = options['moduli']

        else:
            factory = ConchFactory(_portal)

        return internet.TCPServer(int(options["port"]), factory)


# Now construct an object which *provides* the relevant interfaces
# The name of this variable is irrelevant, as long as there is *some*
# name bound to a provider of IPlugin and IServiceMaker.

serviceMaker = CSFTPServiceMaker()
