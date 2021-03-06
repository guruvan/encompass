#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@ecdsa.org
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.


import threading, time, Queue, os, sys, shutil
from util import user_dir, appdata_dir, print_error
from bitcoin import *
import chainparams

class Blockchain(threading.Thread):

    def __init__(self, config, network, active_chain):
        threading.Thread.__init__(self)
        self.daemon = True
        self.config = config

        self.active_chain = active_chain
        self.chunk_size = self.active_chain.chunk_size

        self.network = network
        self.lock = threading.Lock()
        self.local_height = 0
        self.running = False
        self.headers_url = self.active_chain.headers_url
        self.set_local_height()
        self.queue = Queue.Queue()


    def height(self):
        return self.local_height


    def stop(self):
        with self.lock: self.running = False


    def is_running(self):
        with self.lock: return self.running


    def run(self):
        self.init_headers_file()
        self.set_local_height()
        print_error( "blocks:", self.local_height )

        with self.lock:
            self.running = True

        while self.is_running():

            try:
                result = self.queue.get()
            except Queue.Empty:
                continue

            if not result: continue

            i, header = result
            if not header: continue

            height = header.get('block_height')

            if height <= self.local_height:
                continue

            if height > self.local_height + 50:
                if not self.get_and_verify_chunks(i, header, height):
                    continue

            if height > self.local_height:
                # get missing parts from interface (until it connects to my chain)
                chain = self.get_chain( i, header )

                # skip that server if the result is not consistent
                if not chain:
                    print_error('e')
                    continue

                # verify the chain
                if self.verify_chain( chain ):
                    print_error("height:", height, i.server)
                    for header in chain:
                        self.save_header(header)
                else:
                    print_error("error", i.server)
                    # todo: dismiss that server
                    continue


            self.network.new_blockchain_height(height, i)




    def verify_chain(self, chain):

        return self.active_chain.verify_chain(chain)
#        first_header = chain[0]
#        prev_header = self.read_header(first_header.get('block_height') -1)
#
#        for header in chain:
#
#            height = header.get('block_height')
#
#            prev_hash = self.hash_header(prev_header)
#            bits, target = self.get_target(height/2016, chain)
#            _hash = self.hash_header(header)
#            try:
#                assert prev_hash == header.get('prev_block_hash')
#                assert bits == header.get('bits')
#                assert int('0x'+_hash,16) < target
#            except Exception:
#                return False
#
#            prev_header = header
#
#        return True



    def verify_chunk(self, index, hexdata):
        self.active_chain.verify_chunk(index, hexdata)
        self.set_local_height()
#        data = hexdata.decode('hex')
#        height = index*2016
#        num = len(data)/80
#
#        if index == 0:
#            previous_hash = ("0"*64)
#        else:
#            prev_header = self.read_header(index*2016-1)
#            if prev_header is None: raise
#            previous_hash = self.hash_header(prev_header)
#
#        bits, target = self.get_target(index)
#
#        for i in range(num):
#            height = index*2016 + i
#            raw_header = data[i*80:(i+1)*80]
#            header = self.header_from_string(raw_header)
#            _hash = self.hash_header(header)
#            assert previous_hash == header.get('prev_block_hash')
#            assert bits == header.get('bits')
#            assert int('0x'+_hash,16) < target
#
#            previous_header = header
#            previous_hash = _hash
#
#        self.save_chunk(index, data)
#        print_error("validated chunk %d"%height)



    def header_to_string(self, res):
        return self.active_chain.header_to_string(res)
#        s = int_to_hex(res.get('version'),4) \
#            + rev_hex(res.get('prev_block_hash')) \
#            + rev_hex(res.get('merkle_root')) \
#            + int_to_hex(int(res.get('timestamp')),4) \
#            + int_to_hex(int(res.get('bits')),4) \
#            + int_to_hex(int(res.get('nonce')),4)
#        return s


    def header_from_string(self, s):
        return self.active_chain.header_from_string(s)
#        hex_to_int = lambda s: int('0x' + s[::-1].encode('hex'), 16)
#        h = {}
#        h['version'] = hex_to_int(s[0:4])
#        h['prev_block_hash'] = hash_encode(s[4:36])
#        h['merkle_root'] = hash_encode(s[36:68])
#        h['timestamp'] = hex_to_int(s[68:72])
#        h['bits'] = hex_to_int(s[72:76])
#        h['nonce'] = hex_to_int(s[76:80])
#        return h

    def hash_header(self, header):
        return self.active_chain.hash_header(header)
#        return rev_hex(Hash(self.header_to_string(header).decode('hex')).encode('hex'))

    def path(self):
        headers_file_name = '_'.join(['blockchain_headers', self.active_chain.code.lower()])
        return os.path.join( self.config.path, headers_file_name)

    def init_headers_file(self):
        filename = self.path()
        if os.path.exists(filename):
            self.active_chain.set_headers_path(filename)
            return

        try:
            import urllib, socket
            socket.setdefaulttimeout(30)
            print_error("downloading ", self.headers_url )
            urllib.urlretrieve(self.headers_url, filename)
            print_error("done.")
        except Exception:
            print_error( "download failed. creating file", filename )
            open(filename,'wb+').close()
        self.active_chain.set_headers_path(self.path())

    def save_chunk(self, index, chunk):
        self.active_chain.save_chunk(index, chunk)
#        filename = self.path()
#        f = open(filename,'rb+')
#        f.seek(index*2016*80)
#        h = f.write(chunk)
#        f.close()
        self.set_local_height()

    def save_header(self, header):
        self.active_chain.save_header(header)
#        data = self.header_to_string(header).decode('hex')
#        assert len(data) == 80
#        height = header.get('block_height')
#        filename = self.path()
#        f = open(filename,'rb+')
#        f.seek(height*80)
#        h = f.write(data)
#        f.close()
        self.set_local_height()


    def set_local_height(self):
        name = self.path()
        if os.path.exists(name):
            h = os.path.getsize(name)/80 - 1
            if self.local_height != h:
                self.local_height = h


    def read_header(self, block_height):
        return self.active_chain.read_header(block_height)
#        name = self.path()
#        if os.path.exists(name):
#            f = open(name,'rb')
#            f.seek(block_height*80)
#            h = f.read(80)
###            f.close()
#            if len(h) == 80:
#                h = self.header_from_string(h)
#                return h


    def get_target(self, index, chain=None):
        return self.active_chain.get_target(index, chain)


    def request_header(self, i, h, queue):
        print_error("requesting header %d from %s"%(h, i.server))
        i.send_request({'method':'blockchain.block.get_header', 'params':[h]}, queue)

    def retrieve_request(self, queue):
        while True:
            try:
                ir = queue.get(timeout=1)
            except Queue.Empty:
                print_error('blockchain: request timeout')
                continue
            i, r = ir
            result = r['result']
            return result

    def get_chain(self, interface, final_header):

        header = final_header
        chain = [ final_header ]
        requested_header = False
        queue = Queue.Queue()

        while self.is_running():

            if requested_header:
                header = self.retrieve_request(queue)
                if not header: return
                chain = [ header ] + chain
                requested_header = False

            height = header.get('block_height')
            previous_header = self.read_header(height -1)
            if not previous_header:
                self.request_header(interface, height - 1, queue)
                requested_header = True
                continue

            # verify that it connects to my chain
            prev_hash = self.hash_header(previous_header)
            if prev_hash != header.get('prev_block_hash'):
                print_error("reorg")
                # Call reorg_handler if it exists
                try:
                    self.active_chain.reorg_handler(self.local_height)
                    self.set_local_height()
                    return None
                except AttributeError:
                    self.request_header(interface, height - 1, queue)
                    requested_header = True
                    continue

            else:
                # the chain is complete
                return chain


    def get_and_verify_chunks(self, i, header, height):

        queue = Queue.Queue()
        min_index = (self.local_height + 1)/self.chunk_size
        max_index = (height + 1)/self.chunk_size
        n = min_index
        while n < max_index + 1:
            print_error( "Requesting chunk:", n )
            i.send_request({'method':'blockchain.block.get_chunk', 'params':[n]}, queue)
            r = self.retrieve_request(queue)
            try:
                self.verify_chunk(n, r)
                n = n + 1
            except Exception:
                print_error('Verify chunk failed!')
                n = n - 1
                if n < 0:
                    return False

        return True
