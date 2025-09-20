#!/usr/bin/env python3
import asyncio, websockets, json, secrets, time, logging
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class XsukaxChatServer:
    def __init__(self):
        self.users = {}  # user_id -> websocket
        self.user_data = {}  # user_id -> {websocket, public_key, last_seen}
        self.friends = defaultdict(set)  # user_id -> set of friend_user_ids
        self.friend_requests = defaultdict(list)  # user_id -> list of pending requests
        self.messages = defaultdict(list)  # conversation_id -> list of messages
        self.key_status = {}  # user_id -> {private_key_loaded, public_key_loaded}
        
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
            self.user_data[user_id] = {
                'websocket': websocket, 
                'public_key': None,
                'last_seen': time.time()
            }
            self.key_status[user_id] = {
                'private_key_loaded': False,
                'public_key_loaded': False
            }
            
            await websocket.send(json.dumps({
                'type': 'user_id_assigned', 
                'user_id': user_id
            }))
            logging.info(f"Assigned ID {user_id} to client")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get('action')
                    logging.info(f"Action: {action} from {user_id}")
                    
                    # Update last seen
                    if user_id in self.user_data:
                        self.user_data[user_id]['last_seen'] = time.time()
                    
                    if action == 'ping':
                        await self.handle_ping(user_id)
                    elif action == 'set_public_key':
                        await self.set_public_key(user_id, data)
                    elif action == 'set_key_status':
                        await self.set_key_status(user_id, data)
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
                    elif action == 'get_key_status':
                        await self.get_key_status(user_id)
                    else:
                        await self.send_error(user_id, f"Unknown action: {action}")
                        
                except json.JSONDecodeError:
                    logging.error(f"Invalid JSON from {user_id}")
                    await self.send_error(user_id, "Invalid JSON format")
                except Exception as e:
                    logging.error(f"Error processing message from {user_id}: {e}")
                    await self.send_error(user_id, f"Server error: {str(e)}")
                    
        except websockets.exceptions.ConnectionClosed:
            logging.info(f"Client {user_id} disconnected normally")
        except Exception as e:
            logging.error(f"Connection error for {user_id}: {e}")
        finally:
            if user_id:
                await self.cleanup_user(user_id)
                
    async def handle_ping(self, user_id):
        """Handle ping request"""
        try:
            await self.users[user_id].send(json.dumps({'type': 'pong'}))
        except Exception as e:
            logging.error(f"Error sending pong to {user_id}: {e}")
                
    async def send_error(self, user_id, message):
        """Send error message to user"""
        try:
            if user_id in self.users:
                await self.users[user_id].send(json.dumps({
                    'type': 'error', 
                    'message': message
                }))
        except Exception as e:
            logging.error(f"Error sending error message to {user_id}: {e}")
            
    async def set_public_key(self, user_id, data):
        """Set user's public key"""
        try:
            public_key = data.get('public_key')
            if not public_key:
                await self.send_error(user_id, "Public key is required")
                return
                
            if user_id in self.user_data:
                self.user_data[user_id]['public_key'] = public_key
                self.key_status[user_id]['public_key_loaded'] = True
                
                response = {
                    'type': 'public_key_set', 
                    'success': True,
                    'key_status': self.key_status[user_id]
                }
                await self.users[user_id].send(json.dumps(response))
                logging.info(f"Public key set for {user_id}")
            else:
                await self.send_error(user_id, "User not found")
        except Exception as e:
            logging.error(f"Error setting public key for {user_id}: {e}")
            await self.send_error(user_id, f"Failed to set public key: {str(e)}")
            
    async def set_key_status(self, user_id, data):
        """Update user's key loading status"""
        try:
            private_loaded = data.get('private_key_loaded', False)
            public_loaded = data.get('public_key_loaded', False)
            
            if user_id in self.key_status:
                self.key_status[user_id]['private_key_loaded'] = private_loaded
                if public_loaded:
                    self.key_status[user_id]['public_key_loaded'] = public_loaded
                    
                response = {
                    'type': 'key_status_updated',
                    'key_status': self.key_status[user_id]
                }
                await self.users[user_id].send(json.dumps(response))
        except Exception as e:
            logging.error(f"Error updating key status for {user_id}: {e}")
            
    async def get_key_status(self, user_id):
        """Get user's key status"""
        try:
            status = self.key_status.get(user_id, {
                'private_key_loaded': False,
                'public_key_loaded': False
            })
            response = {
                'type': 'key_status',
                'key_status': status
            }
            await self.users[user_id].send(json.dumps(response))
        except Exception as e:
            logging.error(f"Error getting key status for {user_id}: {e}")
            
    async def send_friend_request(self, sender_id, data):
        """Send friend request to target user"""
        try:
            target_id = data.get('target_id', '').upper().strip()
            
            if not target_id or len(target_id) != 6:
                await self.send_error(sender_id, "Invalid user ID format")
                return
                
            if target_id not in self.users:
                await self.send_error(sender_id, "User ID not found or offline")
                return
                
            if target_id == sender_id:
                await self.send_error(sender_id, "Cannot add yourself as friend")
                return
                
            if target_id in self.friends[sender_id]:
                await self.send_error(sender_id, "Already friends with this user")
                return
                
            # Check if request already exists
            existing_requests = [req for req in self.friend_requests[target_id] 
                               if req['sender_id'] == sender_id]
            if existing_requests:
                await self.send_error(sender_id, "Friend request already sent")
                return
                
            # Add friend request
            request_data = {
                'sender_id': sender_id, 
                'timestamp': time.time()
            }
            self.friend_requests[target_id].append(request_data)
            
            # Notify target user
            if target_id in self.users:
                notification = {
                    'type': 'friend_request_received', 
                    'sender_id': sender_id,
                    'timestamp': request_data['timestamp']
                }
                await self.users[target_id].send(json.dumps(notification))
                
            response = {
                'type': 'friend_request_sent', 
                'target_id': target_id
            }
            await self.users[sender_id].send(json.dumps(response))
            logging.info(f"Friend request sent from {sender_id} to {target_id}")
            
        except Exception as e:
            logging.error(f"Error sending friend request from {sender_id}: {e}")
            await self.send_error(sender_id, f"Failed to send friend request: {str(e)}")
        
    async def respond_friend_request(self, user_id, data):
        """Respond to friend request"""
        try:
            sender_id = data.get('sender_id')
            accepted = data.get('accepted', False)
            
            if not sender_id:
                await self.send_error(user_id, "Sender ID is required")
                return
            
            # Remove request
            original_count = len(self.friend_requests[user_id])
            self.friend_requests[user_id] = [req for req in self.friend_requests[user_id] 
                                           if req['sender_id'] != sender_id]
            
            if len(self.friend_requests[user_id]) == original_count:
                await self.send_error(user_id, "Friend request not found")
                return
            
            if accepted:
                # Add as friends
                self.friends[user_id].add(sender_id)
                self.friends[sender_id].add(user_id)
                
                # Notify both users
                response_to_accepter = {
                    'type': 'friend_added',
                    'friend_id': sender_id,
                    'friend_public_key': self.user_data.get(sender_id, {}).get('public_key')
                }
                await self.users[user_id].send(json.dumps(response_to_accepter))
                
                if sender_id in self.users:
                    response_to_sender = {
                        'type': 'friend_added',
                        'friend_id': user_id,
                        'friend_public_key': self.user_data.get(user_id, {}).get('public_key')
                    }
                    await self.users[sender_id].send(json.dumps(response_to_sender))
                    
                logging.info(f"Friend request accepted: {sender_id} and {user_id} are now friends")
            else:
                # Notify sender of rejection
                if sender_id in self.users:
                    response = {
                        'type': 'friend_request_rejected', 
                        'user_id': user_id
                    }
                    await self.users[sender_id].send(json.dumps(response))
                    
                logging.info(f"Friend request rejected: {sender_id} -> {user_id}")
                
        except Exception as e:
            logging.error(f"Error responding to friend request for {user_id}: {e}")
            await self.send_error(user_id, f"Failed to respond to friend request: {str(e)}")
                
    async def send_message(self, sender_id, data):
        """Send encrypted message to friend"""
        try:
            target_id = data.get('target_id')
            encrypted_message = data.get('encrypted_message')
            
            if not target_id:
                await self.send_error(sender_id, "Target user ID is required")
                return
                
            if not encrypted_message:
                await self.send_error(sender_id, "Encrypted message is required")
                return
            
            if target_id not in self.friends[sender_id]:
                await self.send_error(sender_id, "Not friends with this user")
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
            logging.info(f"Message sent from {sender_id} to {target_id}")
            
        except Exception as e:
            logging.error(f"Error sending message from {sender_id}: {e}")
            await self.send_error(sender_id, f"Failed to send message: {str(e)}")
        
    async def get_friends(self, user_id):
        """Get user's friends list"""
        try:
            friends_data = []
            for friend_id in self.friends[user_id]:
                friend_info = {
                    'user_id': friend_id,
                    'public_key': self.user_data.get(friend_id, {}).get('public_key'),
                    'last_seen': self.user_data.get(friend_id, {}).get('last_seen'),
                    'online': friend_id in self.users
                }
                friends_data.append(friend_info)
                
            response = {
                'type': 'friends_list', 
                'friends': friends_data
            }
            await self.users[user_id].send(json.dumps(response))
            logging.info(f"Friends list sent to {user_id} ({len(friends_data)} friends)")
            
        except Exception as e:
            logging.error(f"Error getting friends for {user_id}: {e}")
            await self.send_error(user_id, f"Failed to get friends list: {str(e)}")
        
    async def get_messages(self, user_id, data):
        """Get conversation messages with friend"""
        try:
            target_id = data.get('target_id')
            
            if not target_id:
                await self.send_error(user_id, "Target user ID is required")
                return
                
            if target_id not in self.friends[user_id]:
                await self.send_error(user_id, "Not friends with this user")
                return
                
            conversation_id = self.get_conversation_id(user_id, target_id)
            messages = self.messages.get(conversation_id, [])
            
            response = {
                'type': 'conversation_messages', 
                'target_id': target_id, 
                'messages': messages,
                'message_count': len(messages)
            }
            await self.users[user_id].send(json.dumps(response))
            logging.info(f"Sent {len(messages)} messages to {user_id} for conversation with {target_id}")
            
        except Exception as e:
            logging.error(f"Error getting messages for {user_id}: {e}")
            await self.send_error(user_id, f"Failed to get messages: {str(e)}")
        
    async def cleanup_user(self, user_id):
        """Clean up user data when disconnecting"""
        try:
            if user_id in self.users:
                del self.users[user_id]
            if user_id in self.user_data:
                # Keep user data for offline access, just update last seen
                self.user_data[user_id]['last_seen'] = time.time()
            logging.info(f"Cleaned up user {user_id}")
        except Exception as e:
            logging.error(f"Error cleaning up user {user_id}: {e}")

async def main():
    """Main server function"""
    server = XsukaxChatServer()
    host = "0.0.0.0"
    port = 8765
    
    logging.info(f"Starting xsukax PGP Secure Chat Server on ws://{host}:{port}")
    
    try:
        async with websockets.serve(
            server.handle_client, 
            host, 
            port,
            ping_interval=30,
            ping_timeout=10,
            close_timeout=10
        ):
            logging.info("✓ xsukax Chat Server is running and accepting connections")
            logging.info("Server features:")
            logging.info("  - PGP key management with passphrase support")
            logging.info("  - End-to-end encrypted messaging")
            logging.info("  - Friend request system")
            logging.info("  - Message persistence")
            logging.info("  - Connection health monitoring")
            
            # Keep server running
            await asyncio.Future()
            
    except KeyboardInterrupt:
        logging.info("Server shutdown requested by user")
    except Exception as e:
        logging.error(f"Server startup error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        exit(1)
