

from twisted.internet import reactor
from twisted.web import xmlrpc


class AbstractTransportXMLRPCServer(xmlrpc.XMLRPC):
    
    def xmlrpc_set_my_id(self, user_id):
        """
        """
        return True
    
    def xmlrpc_receive(self, options=None):
        """
        """
        return True
    
    def xmlrpc_send_file(self, filename, host):
        """
        """
        return True

    def xmlrpc_send_file_single(self, filename, host):
        """
        """
        return True

    def xmlrpc_send_message(self, data, host):
        """
        """
        return True

    def xmlrpc_connect_to_host(self, host, my_info):
        """
        """
        return True

    def xmlrpc_disconnect_from_host(self, host):
        """
        """
        return True
    
    def xmlrpc_cancel_file_receiving(self, transferID):
        """
        """
        return True
        
    def xmlrpc_cancel_file_sending(self, transferID):
        """
        """
        return True
        
    def xmlrpc_list_sessions(self):
        """
        """
        return True
        
    def xmlrpc_list_transfers(self):
        """
        """
        return True

    def xmlrpc_set_session_bandwidth_out(self, bytes_per_second):
        """
        """
        return True

    def xmlrpc_set_session_bandwidth_in(self, bytes_per_second):
        """
        """
        return True
        
    def xmlrpc_set_total_bandwidth_out(self, bytes_per_second):
        """
        """
        return True
        
    def xmlrpc_set_total_bandwidth_in(self, bytes_per_second):
        """
        """
        return True
        
    def xmlrpc_disconnect(self):
        """
        """
        return True
        
    def xmlrpc_shutdown(self):
        """
        """
        return True

        
