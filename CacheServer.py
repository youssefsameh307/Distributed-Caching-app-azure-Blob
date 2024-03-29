import asyncio
import os
import random
import socket
import sys
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import BlobClient
from enum import Enum
import time
import socket
import math


class CacheCell:
    def __init__(self, data, meta_data):
        self.data = data
        self.meta_data = meta_data

    def __str__(self):
        return "Data: " + str(self.data) + "\tMeta Data: " + str(self.meta_data)
    
    def getData(self):
        return self.data
    
    def getMetaData(self,key):
        return self.meta_data[key]
    
    def setData(self,data):
        self.data = data

class onDiskCacheCell:
    def __init__(self, data, meta_data, path, key):
        self.path = path
        self.key = key
        self.data = os.path.join(self.path, self.key)
        self.meta_data = meta_data
        print('creating new cell with path: ', self.data)
        try:
            print('started')
            with open(self.data, 'w') as file:
                file.write(str(data))
                print('finished for path', self.data)
        except:
            print("error writing to file")
    
    def __str__(self):
        return "Data: " + str(self.data) + "\tMeta Data: " + str(self.meta_data) + "\tPath: " + str(self.path) + "\tKey: " + str(self.key)
    
    def getData(self):
        data=None
        try:
            with open(self.data, 'r') as file:
                data = file.read()
        except:
            print("error reading file")
            data = None
        return data
    
    def getMetaData(self,key):
        return self.meta_data[key]
    
    def setData(self, data):
        try:
            with open(self.data, 'w') as file:
                file.write(str(data))
        except:
            print("error writing to file")

class replacement_policy_enum(Enum):
    LRU = 1
    MRU = 3
    LFU = 2

class Cache:
    def __init__(self, maxSize, replacement_policy, patience,port,mode):
        self.maxSize = maxSize
        self.patience = patience
        self.replacement_policy = replacement_policy
        self.connection_string = "DefaultEndpointsProtocol=https;AccountName=team43project;AccountKey=ECsl3Tug62RLOD9+RAm8Swzff4izvyLgdSEjBbsh/slgGe0cqhdmptUhClOtkrymvIrY/ZMZ48hu+AStpwNLzA==;EndpointSuffix=core.windows.net"
        
        # self.blob_client = BlobClient.from_connection_string(self.connection_string, 'cloud-project', 'cache_database') #container name , blob name

        self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        self.blob_client = self.container_client = self.blob_service_client.get_container_client("cloud-project")

        self.port = str(port)
        self.cache = dict()
        self.mode = mode
        if mode=='onDisk':
            self.path = os.path.join(os.getcwd(), self.port)
            if os.path.exists(self.path):
                for file_name in os.listdir(self.path):
                    file_path = os.path.join(self.path, file_name)
                    os.remove(file_path)
            else:
                os.mkdir(self.port)
    def __str__(self):
        return "Max Size: " + str(self.maxSize) + "\tReplacement Policy: " + str(self.replacement_policy) + "\tCache: " + str(self.cache)
    
    def read_blob(self,fileName):
        try:
            # Download the blob to a stream
            data = self.container_client.get_blob_client(fileName).download_blob().readall()
            # data = self.blob_client.download_blob().readall()
            return data
        except Exception as ex:
            print('Exception:', ex)


    def contact_db(self,key):
        try:
        # Save the file to the container ---- get pages, a page contains 1000 records so a file contains 124 pages
            print('contacting db for key: ', key)
            targetFileNumber = int(key) // 123333
            targetFileName = 'clickbench_id' + str(targetFileNumber)+'.csv'
            
            targetPageNumber = int(key) % 123333 // 1000
            targetS = int(key) // 1000 * 1000
            print("targetS: ",targetS)
            start = targetS
            endKey = targetS + 1000


            file_content = self.read_blob(targetFileName)
            if file_content == None:
                return None

            file_lines = file_content.decode('utf-8').split('\n')
            page = dict()
            print("passed")
            # for i in range(len(file_lines)):
            #     line = file_lines[i]
            #     if line.startswith(key+'\t'):
            #         content = line.split('\t')[1]
            #         for j in range(max(0,i+1-additionalRecords), min(len(file_lines),i+additionalRecords+1)):
            #             nameList = file_lines[j].split('\t')

            #             if len(nameList) < 2:
            #                 return None
                        
            #             additionalList[nameList[0]] = nameList[1]
            #         return content , additionalList
            
            for i in range(len(file_lines)):
                line = file_lines[i]
                if line == '':
                    break
                nameList = line.split('\t')
                
                index = int(nameList[0])
                value = nameList[1]

                if index >= start and index < endKey:
                    page[nameList[0]] = value

                if index >= endKey:
                    print('not found start')
                    break


                if i == len(file_lines) - 1:
                    print('reached end of the file')
                    break
                
            if page.keys() == []:
                return None
            else:
                print("page: ", page.keys())
                print("page len: ", len(page.keys()))
                return page
        except Exception as ex:
            print('Exception in fetch:', ex)
            print('key: ', key)
            print('page', page)
            return None
        # return None

    def get(self, key):
        try:
            print('getting key: ', key)
            targetFileNumber = int(key) // 123333
            targetPageNumber = (int(key) % 123333) // 1000
            cache_key = str(targetFileNumber) + "_" + str(targetPageNumber)
            if cache_key not in self.cache.keys() or (key not in self.cache[cache_key].data.keys()):
                # print(self.cache)
                print("not found, contacting database")

                data = self.contact_db(key) # get value from database
                if data == None:
                    print("page not found")
                    return "Doesn't exist in DB", 'F'
                print("finished contacting database got data of size: ", len(data.keys()))
                
                self.set(key, data, True)


                ### todo: check if this block should be above the set statement, it is not incorrect 
                # just design choice when not finding the key in the page
                # corrected with the condition being above
                # if key not in data.keys():
                #     print("key not found in page")
                #     return "Doesn't exist in DB", 'F'
                
                print("got value from database ", data[key])

                ###


                print('passed await')
                return str(data[key]), 'F'
            self.cache[cache_key].meta_data['last use'] = time.time()
            self.cache[cache_key].meta_data['use count'] += 1
            if key not in self.cache[cache_key].data.keys():
                print(f"key: {key} not found in cache page")
                print("cache page: ", self.cache[cache_key].data.keys())
                return "Doesn't exist in DB", 'F'

            return self.cache[cache_key].data[key], 'T'
        except Exception as ex:
            print('Exception in get part:', ex)
            print("cache_cell: ", self.cache[cache_key])
            return None,None
    
    def execute_cache_policy(self):
        if self.replacement_policy == 'lru':
            # Find the least recently used item
            least_recently_used = None
            for key in self.cache.keys():
                if least_recently_used == None:
                    least_recently_used = key
                else:
                    if self.cache[key].getMetaData('last use') < self.cache[least_recently_used].getMetaData('last use'):
                        least_recently_used = key
            # Delete the least recently used item
            if self.mode =='onDisk':
                try:
                    filePath = self.cache[least_recently_used].data
                    print(self.cache[least_recently_used])
                    os.remove(filePath)
                    print("cache File deleted successfully.")
                except OSError as e:
                    print(f"Error deleting the file: {e}")
            del self.cache[least_recently_used]
        elif self.replacement_policy == 'mru':
            # Find the most recently used item
            most_recently_used = None
            for key in self.cache.keys():
                if most_recently_used == None:
                    most_recently_used = key
                else:
                    if self.cache[key].getMetaData('last use') > self.cache[most_recently_used].getMetaData('last use'):
                        most_recently_used = key
            # Delete the most recently used item
            if self.mode =='onDisk':
                try:
                    filePath = self.cache[least_recently_used].data
                    os.remove(filePath)
                    print("cache File deleted successfully.")
                except OSError as e:
                    print(f"Error deleting the file: {e}")
            del self.cache[most_recently_used]
        elif self.replacement_policy == 'lfu':
            # Find the least frequently used item
            least_frequently_used = None
            for key in self.cache.keys():
                if least_frequently_used == None:
                    least_frequently_used = key
                else:
                    if self.cache[key].getMetaData('use count') < self.cache[least_frequently_used].getMetaData('use count'):
                        least_frequently_used = key
            # Delete the least frequently used item
            if self.mode =='onDisk':
                try:
                    filePath = self.cache[least_recently_used].data
                    os.remove(filePath)
                    print("cache File deleted successfully.")
                except OSError as e:
                    print(f"Error deleting the file: {e}")
            del self.cache[least_frequently_used]
        else:
            raise Exception("Invalid replacement policy")

    def set(self, key, data, getFromDB=False):
        print('setting key: ', key)
        myKey = key

        targetFileNumber = int(myKey) // 123333
        targetPageNumber = int(myKey) % 123333 // 1000
        cache_key = str(targetFileNumber) + "_" + str(targetPageNumber)      

        if getFromDB and len(self.cache) >= self.maxSize:
            self.execute_cache_policy()
            
        # print('creating new cache cell for ', myKey)
        # print(self.mode)

        meta_data1= dict()
        meta_data1['last use'] = time.time()
        meta_data1['use count'] = 0
        meta_data1['patience'] = self.patience
        # if self.mode == 'onDisk':
        #     # print('creating onDiskCacheCell for key: ', myKey)
        #     self.cache[myKey] = onDiskCacheCell(data, meta_data1, self.path, myKey)
        
        if not getFromDB and (not cache_key in self.cache.keys()):
            
            if len(self.cache) >= self.maxSize:
                self.execute_cache_policy()
            
            page = self.contact_db(myKey)
            if page == None:
                page = dict()
            print("set record: ",data)
            page[myKey] = data # care here
            data = page
            getFromDB = True


        if getFromDB: # unfound get 
            print("getting new data from DB")
            print("size of new data: ", len(data.keys()))
            cacheData = data
            meta=dict()
            meta['last use'] = time.time()
            meta['use count'] = 0
            meta['patience'] = self.patience
            self.cache[cache_key] = CacheCell(cacheData, meta)
        else:   # set
            print("setting data: ", data)
            # print("size of prev cacheData: ", len(cacheData.keys()))
            oldUseCount = self.cache[cache_key].meta_data['use count']
            cacheData = self.cache[cache_key].getData()
            print("size of prev cacheData: ", len(cacheData.keys()))
            
            cacheData[myKey] = data
            meta=dict()
            
            meta['last use'] = time.time()
            meta['use count'] = oldUseCount
            meta['patience'] = self.patience
            print("final set value is: ", cacheData)
            self.cache[cache_key] = CacheCell(cacheData, meta)
        


async def handle_loadbalancer_request(reader, writer):
    addr = writer.get_extra_info('peername')
    # print(f"Accepted connection from {addr}")
    message = None
    response = 'base'
    try:
        while True:
            response = 'base'
            data = await reader.read(100)
            if not data:
                break

            message = data.decode('utf-8')
            print("received message: ", message)
            method = message.split('_')[0]
            key = message.split('_')[1]
            response = ''
            found = None
            if method not in ['set','get']:
                response = None
                break

            if method == 'get':
                response, found = myCache.get(key)
                if response == None:
                    break

            elif method == 'set':
                data = message.split('_')[2:]
                if len(data) == 1:
                    data = data[0]
                else:
                    data = '_'.join(data)

                
                myCache.set(key, data)
                response = 'ACK'
            else:
                response = None
                break

            # fill with cache logic
            if found != None:
                response = found + response
            print("sending response: ", response)
            writer.write(response.encode('utf-8'))
            print(f"Received message from HTTP Client: {message}")
    except Exception as e:
        print("read abnormal data: ",data)
        print("response when abnormal: ", response)
        print("exceptionL ", e)
        if message != None:
            print("abnormal message ", message)

    finally:
        # print(f"Closing connection from {addr}")
        writer.close()

async def connect_to_load_balancer(loadbalancer_ip,cache_port):
    # Connect to the load balancer
    load_balancer_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    load_balancer_socket.connect((loadbalancer_ip, 8082))  # Adjust the load balancer's address and port
    load_balancer_socket.sendall(str(cache_port).encode('utf-8'))
    print(f"Sent cache_port {cache_port} to the Load Balancer")
    load_balancer_socket.close()
    print("Connection to the Load Balancer closed")

async def main(mode,cache_port,replacement_policy, size):
    global myCache
    # myCache = Cache(5, replacement_policy_enum.LRU, 2,cache_port, mode)
    myCache = Cache(size, replacement_policy, 0,cache_port, mode)
    lbip = '20.113.69.217'
    if mode == 'onmem':
        lbip = 'localhost' 
    await connect_to_load_balancer(lbip,cache_port)
    print('cache_port ', cache_port)
    server = await asyncio.start_server(
        handle_loadbalancer_request, '0.0.0.0', cache_port)  # Adjust the port as needed

    addr = server.sockets[0].getsockname()
    print(f"Cache Server listening on {addr}")

    async with server:
        await server.serve_forever()

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python CacheServer.py <on_code> <cache_port> <replacement_policy> <cache_size>")
        sys.exit(1)

    rePo = ['lfu','mru','lru']
    if sys.argv[3] not in rePo:
        print("Usage: <replacement_policy> should be one of ['lfu','mru','lru']")
        sys.exit(1)
    replacement_policy = str(sys.argv[3])
    # print(replacement_policy_enum.LRU)
    cache_port = int(sys.argv[2])
    mode = str(sys.argv[1])
    size = int(sys.argv[4])
    asyncio.run(main(mode, cache_port, replacement_policy,size))
