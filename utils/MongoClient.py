import time
import pymongo
from pymongo.collection import ReturnDocument
from utils.Config import Config
from utils.Logger import *
from utils.Singleton import Singleton
from cachetools import cached, LRUCache, TTLCache
from bson import json_util
import uuid


class MongoDBClient(metaclass=Singleton):
    def __init__(self) -> None:
        self.config = Config()
        self.client = pymongo.MongoClient(self.config.get("MONGO_URL"))
        self.tgcalls = self.client["tgcalls"]

    def fetchRunTimeData(self):
        try:
            return self.tgcalls.runtime_data.find_one(
                {"service": self.config.get("source")}
            )
        except Exception as ex:
            logException("Error in fetchRunTimeData : {}".format(ex))
            raise Exception(ex)

    def get_all_chats(self):
        try:
            data = self.tgcalls.tgcalls_chats.find({})
            return list(data if data is not None else [])
        except Exception as ex:
            logException(f"Error in get_active_chats : {ex}")

    @cached(cache=TTLCache(maxsize=1024, ttl=30))
    @logger.catch
    def add_tgcalls_users(self, chat_id, userInfo):
        userInfo = json_util.loads(userInfo)
        user = self.tgcalls.tgcalls_users.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": {"updated_at": datetime.now()}},
            return_document=ReturnDocument.AFTER,
        )
        if not user:
            userInfo["created_at"] = datetime.now()
            userInfo["updated_at"] = datetime.now()
            self.tgcalls.tgcalls_users.insert_one(userInfo)
            return userInfo
        return user

    @cached(cache=TTLCache(maxsize=1024, ttl=30))
    @logger.catch
    def add_tgcalls_chats(self, chat_id, chatInfo):
        chatInfo = json_util.loads(chatInfo)
        chat = self.tgcalls.tgcalls_chats.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": {"updated_at": datetime.now()}},
            return_document=ReturnDocument.AFTER,
        )
        if not chat:
            chatInfo["created_at"] = datetime.now()
            chatInfo["updated_at"] = datetime.now()
            self.tgcalls.tgcalls_chats.insert_one(chatInfo)
            return chatInfo
        return chat

    @logger.catch
    def generate_auth_document(self, chat_id, user_id):
        doc = {
            "user_id": user_id,
            "chat_id": chat_id,
            "uuid": str(uuid.uuid4()).split("-")[-1],
            "time": int(time.time()),
        }
        self.tgcalls.tgcalls_temp_auth.insert_one(doc)
        return doc

    @logger.catch
    def get_temp_auths(self, user_id):
        return list(
            self.tgcalls.tgcalls_temp_auth.find(
                {"user_id": user_id, "time": {"$gte": int(time.time()) - (15 * 60)}}
            ).sort("time", pymongo.DESCENDING)
        )

    @logger.catch
    def save_user_bot_details(
        self, chat_id, user_id, user_name, api_id, api_hash, session_string
    ):
        user_bot = (
            {
                "apidId": api_id,
                "apiHash": api_hash,
                "sessionId": session_string,
                "userId": user_id,
                "userName": user_name,
            },
        )
        return self.tgcalls.tgcalls_chats.find_one_and_update(
            {"chat_id": chat_id},
            {"$set": {"userBot": user_bot}},
            return_document=ReturnDocument.AFTER,
        )

    def add_song_playbacks(self, songInfo, requestedUser, docId):
        try:
            if self.config.get("env") == "prod":
                self.tgcalls.tgcalls_playbacks.insert_one(
                    {
                        "tgcalls_chat": docId,
                        "song": songInfo,
                        "requested_by": requestedUser,
                        "updated_at": datetime.now(),
                    }
                )
        except Exception as ex:
            logException(
                f"Error in add_song_playbacks : {ex} , {songInfo}, {requestedUser}, {docId}"
            )

    def update_admins(self, chatId, admins):
        try:
            if isinstance(admins, list) is True:
                data = self.tgcalls.tgcalls_chats.find_one_and_update(
                    {"chat_id": chatId},
                    {"$set": {"admins": admins}},
                    return_document=ReturnDocument.AFTER,
                )
            elif isinstance(admins, dict) is True:
                data = self.tgcalls.tgcalls_chats.find_one_and_update(
                    {"chat_id": chatId},
                    {"$push": {"admins": admins}},
                    return_document=ReturnDocument.AFTER,
                )
            else:
                raise Exception(f"Invalid type to add admin : {chatId} , {admins} ")
            self.config.updateChat(data)
        except Exception as ex:
            logException(f"Error in update_admins : {ex}")

    def remove_admins(self, chatId, adminToRemove):
        try:
            if isinstance(adminToRemove, dict) is True:
                data = self.tgcalls.tgcalls_chats.find_one_and_update(
                    {"chat_id": chatId},
                    {"$pull": {"admins": {"chat_id": adminToRemove["chat_id"]}}},
                    return_document=ReturnDocument.AFTER,
                )
            else:
                raise Exception(
                    f"Invalid type to remove admin : {chatId} , {adminToRemove} "
                )
            self.config.updateChat(data)
        except Exception as ex:
            logException(f"Error in remove_admins : {ex}")

    def update_admin_mode(self, chatId, newStatus):
        try:
            if isinstance(newStatus, bool) is True:
                data = self.tgcalls.tgcalls_chats.find_one_and_update(
                    {"chat_id": chatId},
                    {"$set": {"admin_mode": newStatus}},
                    return_document=ReturnDocument.AFTER,
                )
            else:
                raise Exception(
                    f"Invalid type to update admin mode : {chatId} , {newStatus} "
                )
            self.config.updateChat(data)
        except Exception as ex:
            logException(f"Error in update_admin_mode : {ex}")

    def chats_to_disconnect(self):
        try:
            from datetime import timedelta

            agg = [
                {
                    "$match": {
                        "updated_at": {
                            "$lt": (datetime.now() - timedelta(hours=0, minutes=30))
                        }
                    }
                },
                {"$group": {"_id": "$tgcalls_chat"}},
                {
                    "$lookup": {
                        "from": "tgcalls_chats",
                        "localField": "_id",
                        "foreignField": "_id",
                        "as": "chat",
                    }
                },
                {"$unwind": {"path": "$chat", "preserveNullAndEmptyArrays": True}},
            ]
            if self.config.get("env") == "local":
                agg.append({"$match": {"chat.testing": True}})
            result = self.tgcalls["tgcalls_playbacks"].aggregate(agg)
            return list(result)
        except Exception as ex:
            logException(f"Error in getting chats : {ex}")
