#!/usr/bin/python
#events.py
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#

import os
import sys
import time


_OutputFunc = None


def init(output_func):
    global _OutputFunc
    _OutputFunc = output_func


def call(typ, module, message, text=''):
    global _OutputFunc
    if _OutputFunc is None:
        return
    _OutputFunc('event %s (((%s))) [[[%s]]] %s' % (typ, module, message, text))

def info(module, message, text=''):
    call('info', module, message, text)
    

def notify(module, message, text=''):
    call('notify', module, message, text)


def warning(module, message, text=''):
    call('warning', module, message, text)

    
   