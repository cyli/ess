from twisted.python.filepath import FilePath
import os

clientPrivKey = """
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAz8vTCxq+gBO4LlH65h4uDmgr6tE00VVCZTVLtkSUUHNvaLCn
6ihEQG89MeydrvsSPDWRF66Om6kMk5pAWEJe2j5CkgkrgHrEWI51cBTojXa4CgBL
q6IZIG7hXYoDpJyTqInmYRAMoWOlpqFZ7DmIpW8hEOjX/0Gp0lJ/Qg/Yek9s1zH0
B0r7aJLmM6j/rysJnZct5OuKV4Wr8FjzzQqIr/4jSR2kfEYZBn+vkU/CrgXuakCY
XmlQDizFpi83AqihLuzbSSTsgtKTMOe4OjKE3X0yfBjRr43w/UdrvSxKGklEaIcr
Q+VIDEAZMCFKd8y2LQPgxrweMY9kVzWkwQk/bQIBIwKCAQBwzbu1kizmcRrXURMs
dsiLemD70Kek1oMg/6zCB/i99YWfO1PW4qi1Q7OBgHLbVRiHFcPLBvz1amXpuiLu
FWaw/ToUwyY+bofYTVWx33bttXnZiyHDkoKrNOC9v/NZXFAoStwmEAbbRLkCr1yz
b7CUUkUmb8W2dBpcO2mnhPHb/j/AzNn53vFui4azAB5x2R/zK6kBuDwo/iYZEQkO
9kv3IPRBnxzdfRo0+iuyzH/Fkg5P2A+J4OHCabTWmNYX8WexW/0kUb3so8JFU/dm
GRpS0sIiPWrg/gQ4+ktld1RGnfCasJJvn9W5cWgD3y31iJpeslnKXM+78Qz7RrOz
bP+rAoGBAPtH/FwZwIOpOHZh+waP2u/Bxkzt0RJjCKAV5xdDmBhJufj6fOJlfrgL
PGZIw0xcaqaCIp3ZkU7ru1lijUCv8RSKiRTPrQNADLTuxCwQzFujSfvieoOdtI+6
o25JNGax1Vw3F6CChn1CljUO7D0PYml7nwZcdVHfZ71evCI+H6EJAoGBANOyybWN
CrsBMP5s/pieb0rLBzBfuZ1YIiP9HJX0n0LHcz/wsYzqkBXCGCE1E8DYL+osnXIb
EVPJyaXgvlD+MMAnx8u9TR+cVNa09Kl6zCEoXiHTztoHmapS8d5avcFtGxIHAdtS
D/A+KdOuSRcP5+z1eqDNFRfCDUuwVZXMmhhFAoGBAIE69tBHwhfTXt3L/XEWyF4L
4lNy/c7xGmD1UkZ6iLwIqMkwXXu/KzoUaDSacxFUGZd2IG5v5FR5O8eRxPyyQXhH
Py9GO7iHVv33Iw9ZGKQoF2uZC86o4IRunTFnegjtvi9sylKMRSp6BBtJgM7x+Bj9
v3+dQ6Zy5OUMJj1/CPO7AoGBAMGNhThGcDXyde/un6F66Wj0I9R0xvZB81Qancru
SHeRyHT5Ud/sZnpLDr9GeHXM+JuWgVJh4/TVv62aR5qCAK+vV5W0Y8UhN5+7Y1kf
0JNYG4ykZVmgjH53uJDH/fKs5YzTNOXHXweJStAqUXQrzLtkGFiA/VeM2PS+eiKP
Lc0LAoGBAKjIte711+LMT3cL6F+HmsK3e1uLVPZ7Wt6QidqHDEF89WBT3x20ddLE
ky9L06qK0SSG0nlzu6CUI3flbARPV1KXH7ZQlk2D2rkV5g5tcFmO61NCVhDKwxiP
uMdy92ZP+FKFRgoczczpNrwRc4ESSpeO/e6rNaC7VjIOaeATLDlh
-----END RSA PRIVATE KEY-----
"""

clientPubKey = """
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAz8vTCxq+gBO4LlH65h4uDmgr6tE00VVCZTVLtkSUUHNvaLCn6ihEQG89MeydrvsSPDWRF66Om6kMk5pAWEJe2j5CkgkrgHrEWI51cBTojXa4CgBLq6IZIG7hXYoDpJyTqInmYRAMoWOlpqFZ7DmIpW8hEOjX/0Gp0lJ/Qg/Yek9s1zH0B0r7aJLmM6j/rysJnZct5OuKV4Wr8FjzzQqIr/4jSR2kfEYZBn+vkU/CrgXuakCYXmlQDizFpi83AqihLuzbSSTsgtKTMOe4OjKE3X0yfBjRr43w/UdrvSxKGklEaIcrQ+VIDEAZMCFKd8y2LQPgxrweMY9kVzWkwQk/bQ==
"""

serverPrivKey = """
-----BEGIN RSA PRIVATE KEY-----
MIIEoQIBAAKCAQEAleRTVuo9riuBuqwW39tcPYsqM9+BKiGoHI3/RSST9v8nsfC1
aeH5qGwm6aJIAAIW7iPXWeOa72Gu91uQGnq205up8gI8Urqxpa9XjZqUITA8SrLu
JZEMOppU5OxI4lzu4YEA5HAEMnxDhLu7blJVuHIPyvAxqZEucXqole5cK4dwS3G3
MPoJjrqxYclM0tjxL2JAsCqr6Wcw+7tLnFLKavRnvbFVkEjndosWVquDl6A2r1v6
HdlmVkNT3lt2Uxseq+M9w0n/aF85CykDWWwDBh/A/kadlzuU0KqWhT34Jn3YzD1C
nlcjuOxLl1fX87LG9rhywJct6XVh/dPLm5XpBQIBIwKCAQEAhMLqurI2oZQ/s/eB
+Xkl0BwssZoTUTPAyNWKUy8GtjJznZqvTyc8NhamH2PZXxfLKrIH4ebZr3PG2xaV
k8vGgOj1m9YYLARxdX4Lt+9QACNome7wL+be8hOqRxpscLi2UrQWu7Or8jOMQl0i
WmYuqq4rPrd8cZ3Yracnmr0tEJss+/x/mRQ53+pHkPRtDYhS1R4uxia1DjLsbvDf
to/qI9RldO9rfCLUEybbO9ig0CZEcTMsWnu/eHPsRrjgpXX59C96A1eGWsnQ5MCM
baLOsjQe07cUeTzvmlQxXc9ky0s7EhcfQi89aKBCaqj5dcXIrSHmu8157iGxA63J
RuksBwKBgQDHFpt6LE0AB9gMrcIf0BbSg/4if5IrCez1HGt2LqaTZiEhCT0LIXfT
TL54mVUoRF7A1ril3thsLe3bTc8CXwqsDw2ZxLQ4A7+iOB0r56UpUgwP7Epe6Ej5
vIvSDz+SjoGrvUszW770m5mUOWtEgRkKTrvSUbK4r2txfXBqijfC2wKBgQDAvX9a
YBpUklYBUm8U+7zZ7FKOiq7dvu4orGDpXX1X9SWJ1ZeGwaF/kAwZ1JuVPvU5FsRk
O/Eh+y1tzRaPGDiq/MER+s/dHycWVOggH0jXkApk+alpoe/fI9A6JNpvqjOgCwmA
nQgCjmw61Pw//iXJke8gDnhW6x21CJ8rPS2ZnwKBgEnydENSSHxar1UqmI95LQxc
6V1FU4xUJNAR3sV/CqvG2RrmLJ27+U57lzQbsepiiZgVPUTsXwOcB+O90IvaKIkM
58tmUZEl9riYf90bhn0P2JgzMZD3MQxNWIE43RktneC0Bf0iE7nwpsIGstBNNS+2
2AxKOxFlujF3vApQmF5RAoGAEIVFbiV+mYjizOnPAcxvReEOY/1CMEOQwahgFACy
+OkgeYdWIX5Pq9klm9BlG2vL4FJomuCRAumkzuWxefrDB1d+Q16kGkR/sXT99B/w
TP23v4MdJk+1eYa6E5zCRBXnKvmhupEd8Zct2Sgy4Onl+1WmyDvBLAWGNBaujq14
7+kCgYA2bX5yweSgt2U604aVBjM7TVUOLZvFwXI89Pj+P7aec/o2TgHn4rtx3B0b
4E0WJnLq0Tn/qIDySbmWGqSbolgSMnhG7XBT2v/uEeRxIihJrHal8iNxFcCE8rD2
jvkwk3QeOQTpB36XKREivtpwzrEgMywJPKNoesRrVaPNvenM5A==
-----END RSA PRIVATE KEY-----
"""

serverPubKey = """
ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAleRTVuo9riuBuqwW39tcPYsqM9+BKiGoHI3/RSST9v8nsfC1aeH5qGwm6aJIAAIW7iPXWeOa72Gu91uQGnq205up8gI8Urqxpa9XjZqUITA8SrLuJZEMOppU5OxI4lzu4YEA5HAEMnxDhLu7blJVuHIPyvAxqZEucXqole5cK4dwS3G3MPoJjrqxYclM0tjxL2JAsCqr6Wcw+7tLnFLKavRnvbFVkEjndosWVquDl6A2r1v6HdlmVkNT3lt2Uxseq+M9w0n/aF85CykDWWwDBh/A/kadlzuU0KqWhT34Jn3YzD1CnlcjuOxLl1fX87LG9rhywJct6XVh/dPLm5XpBQ==
"""

# string substitution dict keys needed:  port (port number), hostkeyFile
# (absolute filename of the host key (private), clientPubkeyFile (absolute
# filename of the public key the client will use to log in)
sshd_config = """
Port %(port)d              # Run this server on a different port
ListenAddress 127.0.0.1    # Necessary on some machines
Protocol 2                 # Use ssh protocol-2
HostKey %(hostkeyFile)s    # HostKey (private not public) for protocol 2
LoginGraceTime 5           # shouldn't take very long to log in automatically
PermitRootLogin no
RSAAuthentication yes
PubkeyAuthentication yes

# Just use the public key of the key used to log in
AuthorizedKeysFile  %(clientPubkeyFile)s

ChallengeResponseAuthentication no
PasswordAuthentication no
TCPKeepAlive yes

Subsystem sftp /usr/lib/openssh/sftp-server

UsePAM no                  # Without this, user won't get authenticated
"""

# string substitution dict keys needed: hostname (a string of the hostname
# used to log in), clientPrivkeyFile (absolute filename of the private key
# the client will use to log in)
ssh_config = """
Host %(hostname)s
    HostKeyAlias %(hostname)s
    HostName localhost
    CheckHostIP no
    UserKnownHostsFile /dev/null
    StrictHostKeyChecking no
    IdentityFile %(clientPrivkeyFile)s
    Port %(port)d
    Protocol 2
    HashKnownHosts no
    GSSAPIAuthentication yes
    GSSAPIDelegateCredentials no
"""


def setupConfig(directoryPath, port):
    f = FilePath(directoryPath)
    hostkey = f.child('hostkey')
    hostkey.setContent(serverPrivKey)
    os.chmod(hostkey.path, 0600)
    knownHosts = f.child('clientID.pub')
    knownHosts.setContent(clientPubKey)
    clientID = f.child('clientID')
    clientID.setContent(clientPrivKey)
    os.chmod(clientID.path, 0600)

    hostname = 'localhost.sftp.experimental'

    sshdConfigFile = f.child("sshd_config")
    sshdConfigFile.setContent(sshd_config % {
            'port': port,
            'hostkeyFile': hostkey.path,
            'clientPubkeyFile': knownHosts.path})

    sshConfigFile = f.child("ssh_config")
    sshConfigFile.setContent(ssh_config % {
            'port': port,
            'clientPrivkeyFile': clientID.path,
            'hostname': hostname})

    serverOptions = "-de -f %s" % sshdConfigFile.path
    clientOptions = "-F %s %s" % (sshConfigFile.path, hostname)

    return (serverOptions, clientOptions)

#server command:  /usr/sbin/sshd
#client commands: ssh -F ssh_config localhost.sftp.experimental
#                 sftp -F ssh_config localhost:sftp.experimental
