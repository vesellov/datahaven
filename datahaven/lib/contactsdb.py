#!/usr/bin/python
#contactsdb.py

import dhnio

#-------------------------------------------------------------------------------

_customerids = []      # comes from settings.CustomerIDsFilename()  and that gets from DHN central
_supplierids = []      # comes from settings.SupplierIDsFilename()  and that gets from DHN central
_correspondentids = [] # comes from settings.CorrespondentIDsFilename()

#-------------------------------------------------------------------------------

def suppliers():
    global _supplierids
    return _supplierids

def customers():
    global _customerids
    return _customerids

def contacts():
    return list(set(suppliers()+customers()))

def correspondents():
    global _correspondentids
    return _correspondentids

def contacts_full():
    return list(set(contacts() + correspondents()))

def set_suppliers(idlist):
    global _supplierids
    _supplierids = []
    for idurl in idlist:
        _supplierids.append(idurl.strip())
    # _supplierids = list(idlist)

def set_customers(idlist):
    global _customerids
    _customerids = list(idlist)

def set_correspondents(idlist):
    global _correspondentids
    _correspondentids = list(idlist)

def add_customer(idurl):
    global _customerids
    _customerids.append(idurl)
    return len(_customerids) - 1

def add_supplier(idurl):
    global _supplierids
    _supplierids.append(idurl)
    return len(_supplierids) - 1

def add_correspondent(idurl):
    global _correspondentids
    _correspondentids.append(idurl)
    return len(_correspondentids) - 1

def remove_correspondent(idurl):
    global _correspondentids
    if idurl in _correspondentids:
        _correspondentids.remove(idurl)
        return True
    return False

def clear_suppliers():
    global _supplierids
    _supplierids = [] 

def clear_customers():
    global _customerids
    _customerids = []
    
def clear_correspondents():
    global _correspondentids
    _correspondentids = []

#-------------------------------------------------------------------------------

def is_customer(idurl):
    return idurl in customers()

def is_supplier(idurl):
    return idurl and idurl in suppliers()

def is_correspondent(idurl):
    return idurl in correspondents()

def num_customers():
    return len(customers())

def num_suppliers():
    return len(suppliers())

def supplier(index):
    num = int(index)
    if num>=0 and num < len(suppliers()):
        return suppliers()[num]
    return ''

def customer(index):
    num = int(index)
    if num>=0 and num < len(customers()):
        return customers()[num]
    return ''

def supplier_index(idurl):
    if not idurl:
        return -1
    try:
        index = suppliers().index(idurl)
    except:
        index = -1
    return index

def customer_index(idurl):
    try:
        index = customers().index(idurl)
    except:
        index = -1
    return index

def contact_index(idurl):
    try:
        index = contacts().index(idurl)
    except:
        index = -1
    return index

#-------------------------------------------------------------------------------

def save_suppliers(path):
    dhnio._write_list(path, suppliers())

def save_customers(path):
    dhnio._write_list(path, customers())
    
def save_correspondents(path):
    dhnio._write_list(path, correspondents())

def load_suppliers(path):
    lst = dhnio._read_list(path)
    if lst is None:
        lst = list()
    set_suppliers(lst)

def load_customers(path):
    lst = dhnio._read_list(path)
    if lst is None:
        lst = list()
    set_customers(lst)

def load_correspondents(path):
    lst = dhnio._read_list(path)
    if lst is None:
        lst = list()
    set_correspondents(lst)






