import hashlib
import json
import time

class Block:
    def __init__(self, index, ticket_id, train_id, timestamp, previous_hash):
        self.index = index
        self.ticket_id = ticket_id
        self.train_id = train_id
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.hash = self.calculate_hash()
    
    def calculate_hash(self):
        block_string = json.dumps({
            "index": self.index,
            "ticket_id": self.ticket_id,
            "train_id": self.train_id,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

class Blockchain:
    def __init__(self):
        self.chain = []
        self.create_genesis_block()
    
    def create_genesis_block(self):
        genesis_block = Block(0, "GENESIS", "0", time.time(), "0")
        self.chain.append(genesis_block)
    
    def get_latest_block(self):
        return self.chain[-1]
    
    def add_block(self, ticket_id, train_id):
        latest_block = self.get_latest_block()
        new_block = Block(len(self.chain), ticket_id, train_id, time.time(), latest_block.hash)
        self.chain.append(new_block)
        return new_block
    
    def verify_chain(self):
        for i in range(1, len(self.chain)):
            current_block = self.chain[i]
            previous_block = self.chain[i-1]
            if current_block.hash != current_block.calculate_hash():
                return False
            if current_block.previous_hash != previous_block.hash:
                return False
        return True