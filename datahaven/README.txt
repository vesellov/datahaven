DataHaven.NET
=============

DataHaven.NET is a peer to peer online backup utility.

This is a distributed network for backup data storage. Each participant of the network provides a portion of his hard drive for other users. In exchange, he is able to store his data on other peers.

The redundancy in backup makes it so if someone loses your data, you can rebuild what was lost and give it to someone else to hold. And all of this happens without you having to do a thing - the software keeps your data in safe.

All your data is encrypted before it leaves your computer with a private key your computer generates. No one else can read your data, even DataHaven.NET! Recover data is only one way - download the necessary pieces from computers of other peers and decrypt them with your private key.

DataHaven.NET is written in Python using pure Twisted framework.

http://datahaven.net



Install
=======

Copy folder "datahaven" in any place you want.

To start:

cd datahaven

python dhn.py show



Dependencies
============

python 2.6 or 2.7, python3 is not supported
    http://python.org/download/releases
    
twisted 11.0 or higher: 
    http://twistedmatrix.com
    
pyasn1: 
    http://pyasn1.sourceforge.net
    
pyOpenSSL: 
    https://launchpad.net/pyopenssl
    
pycrypto: 
    https://www.dlitz.net/software/pycrypto/
    
PIL: 
    http://www.pythonware.com/products/pil
    
wxgtk2.8: 
    http://wiki.wxpython.org/InstallingOnUbuntuOrDebian


Or just install those packages if you have them in repos:
    
python
python-twisted
python-pyasn1
python-openssl
python-crypto
python-wxgtk2.8
python-imaging 



Wiki
====

http://datahaven.net/wiki
