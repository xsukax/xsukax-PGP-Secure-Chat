#!/usr/bin/env python3
import asyncio, websockets, json, secrets, time, logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO)

class XsukaxChatServer:
    def __init__(self):
        self.users = {}  # user_id -> websocket
        self.user_data = {}  # user_id -> {websocket, public_key}
        self.friends = defaultdict(set)  # user_id -> set of friend_user_ids
        self.friend_requests = defaultdict(list)  # user_id -> list of pending requests
        self.messages = defaultdict(list)  # conversation_id -> list of messages
        
    def generate_user_id(self):
        """Generate unique 6-character ID"""
        while True:
            user_id = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(6))
            if user_id not in self.users:
                return user_id
                
    def get_conversation_id(self, user1_id, user2_id):
        """Generate consistent conversation ID for two users"""
        return '_'.join(sorted([user1_id, user2_id]))
        
    async def handle_client(self, websocket):
        user_id = None
        try:
            logging.info(f"New client connected: {websocket.remote_address}")
            
            # Generate and send unique ID
            user_id = self.generate_user_id()
            self.users[user_id] = websocket
            self.user_data[user_id] = {'websocket': websocket, 'public_key': None}
            
            await websocket.send(json.dumps({'type': 'user_id_assigned', 'user_id': user_id}))
            logging.info(f"Assigned ID {user_id} to client")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get('action')
                    logging.info(f"Action: {action} from {user_id}")
                    
                    if action == 'ping':
                        await websocket.send(json.dumps({'type': 'pong'}))
                    elif action == 'set_public_key':
                        await self.set_public_key(user_id, data)
                    elif action == 'send_friend_request':
                        await self.send_friend_request(user_id, data)
                    elif action == 'respond_friend_request':
                        await self.respond_friend_request(user_id, data)
                    elif action == 'send_message':
                        await self.send_message(user_id, data)
                    elif action == 'get_friends':
                        await self.get_friends(user_id)
                    elif action == 'get_messages':
                        await self.get_messages(user_id, data)
                        
                except Exception as e:
                    logging.error(f"Error processing message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"Client {user_id} disconnected")
        except Exception as e:
            logging.error(f"Connection error: {e}")
        finally:
            if user_id:
                await self.cleanup_user(user_id)
                
    async def set_public_key(self, user_id, data):
        public_key = data.get('public_key')
        if public_key and user_id in self.user_data:
            self.user_data[user_id]['public_key'] = public_key
            response = {'type': 'public_key_set', 'success': True}
            await self.users[user_id].send(json.dumps(response))
            
    async def send_friend_request(self, sender_id, data):
        target_id = data.get('target_id', '').upper().strip()
        
        if not target_id or target_id not in self.users:
            response = {'type': 'error', 'message': 'User ID not found'}
            await self.users[sender_id].send(json.dumps(response))
            return
            
        if target_id == sender_id:
            response = {'type': 'error', 'message': 'Cannot add yourself'}
            await self.users[sender_id].send(json.dumps(response))
            return
            
        if target_id in self.friends[sender_id]:
            response = {'type': 'error', 'message': 'Already friends'}
            await self.users[sender_id].send(json.dumps(response))
            return
            
        # Check if request already exists
        existing_requests = [req for req in self.friend_requests[target_id] if req['sender_id'] == sender_id]
        if existing_requests:
            response = {'type': 'error', 'message': 'Friend request already sent'}
            await self.users[sender_id].send(json.dumps(response))
            return
            
        # Add friend request
        request_data = {'sender_id': sender_id, 'timestamp': time.time()}
        self.friend_requests[target_id].append(request_data)
        
        # Notify target user
        if target_id in self.users:
            notification = {'type': 'friend_request_received', 'sender_id': sender_id}
            await self.users[target_id].send(json.dumps(notification))
            
        response = {'type': 'friend_request_sent', 'target_id': target_id}
        await self.users[sender_id].send(json.dumps(response))
        
    async def respond_friend_request(self, user_id, data):
        sender_id = data.get('sender_id')
        accepted = data.get('accepted', False)
        
        # Remove request
        self.friend_requests[user_id] = [req for req in self.friend_requests[user_id] if req['sender_id'] != sender_id]
        
        if accepted:
            # Add as friends
            self.friends[user_id].add(sender_id)
            self.friends[sender_id].add(user_id)
            
            # Notify both users (no online status shared)
            response = {
                'type': 'friend_added',
                'friend_id': sender_id,
                'friend_public_key': self.user_data.get(sender_id, {}).get('public_key')
            }
            await self.users[user_id].send(json.dumps(response))
            
            if sender_id in self.users:
                response = {
                    'type': 'friend_added',
                    'friend_id': user_id,
                    'friend_public_key': self.user_data.get(user_id, {}).get('public_key')
                }
                await self.users[sender_id].send(json.dumps(response))
        else:
            # Notify sender of rejection
            if sender_id in self.users:
                response = {'type': 'friend_request_rejected', 'user_id': user_id}
                await self.users[sender_id].send(json.dumps(response))
                
    async def send_message(self, sender_id, data):
        target_id = data.get('target_id')
        encrypted_message = data.get('encrypted_message')
        
        if target_id not in self.friends[sender_id]:
            response = {'type': 'error', 'message': 'Not friends with this user'}
            await self.users[sender_id].send(json.dumps(response))
            return
            
        conversation_id = self.get_conversation_id(sender_id, target_id)
        message_data = {
            'sender_id': sender_id,
            'target_id': target_id,
            'encrypted_message': encrypted_message,
            'timestamp': time.time()
        }
        
        self.messages[conversation_id].append(message_data)
        
        # Send to both users
        notification = {
            'type': 'message_received',
            'sender_id': sender_id,
            'target_id': target_id,
            'encrypted_message': encrypted_message,
            'timestamp': message_data['timestamp']
        }
        
        # Send to target if online
        if target_id in self.users:
            await self.users[target_id].send(json.dumps(notification))
            
        # Confirm to sender
        await self.users[sender_id].send(json.dumps(notification))
        
    async def get_friends(self, user_id):
        friends_data = []
        for friend_id in self.friends[user_id]:
            friend_info = {
                'user_id': friend_id,
                'public_key': self.user_data.get(friend_id, {}).get('public_key')
            }
            friends_data.append(friend_info)
            
        response = {'type': 'friends_list', 'friends': friends_data}
        await self.users[user_id].send(json.dumps(response))
        
    async def get_messages(self, user_id, data):
        target_id = data.get('target_id')
        if target_id not in self.friends[user_id]:
            return
            
        conversation_id = self.get_conversation_id(user_id, target_id)
        messages = self.messages.get(conversation_id, [])
        
        response = {'type': 'conversation_messages', 'target_id': target_id, 'messages': messages}
        await self.users[user_id].send(json.dumps(response))
        
    async def cleanup_user(self, user_id):
        if user_id in self.users:
            del self.users[user_id]
        if user_id in self.user_data:
            del self.user_data[user_id]

async def main():
    server = XsukaxChatServer()
    logging.info("Starting xsukax PGP Secure Chat Server on ws://0.0.0.0:8765")
    
    try:
        async with websockets.serve(server.handle_client, "0.0.0.0", 8765):
            logging.info("✓ xsukax Chat Server is running and accepting connections")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logging.error(f"Server startup error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())