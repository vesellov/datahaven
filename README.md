datahaven
=========

DataHaven.NET is a peer to peer online backup utility.

This is a distributed network for backup data storage. Each participant of the network provides a portion of his hard drive for other users. In exchange, he is able to store his data on other peers.

The redundancy in backup makes it so if someone loses your data, you can rebuild what was lost and give it to someone else to hold. And all of this happens without you having to do a thing - the software keeps your data in safe.

All your data is encrypted before it leaves your computer with a private key your computer generates. No one else can read your data, even DataHaven.NET! Recover data is only one way - download the necessary pieces from computers of other peers and decrypt them with your private key.

DataHaven.NET is written in Python using pure Twisted framework.


Install
=======

Copy folder "datahaven" in any place you want.

To start:
cd datahaven
python dhn.py show



