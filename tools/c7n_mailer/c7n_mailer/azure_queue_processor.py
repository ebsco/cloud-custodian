# Copyright 2018 Capital One Services, LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Azure Queue Message Processing
==============================

"""
import base64
import json
import traceback
import zlib

from .sendgrid_delivery import SendGridDelivery

try:
    from c7n_azure.storage_utils import StorageUtilities
except ImportError:
    StorageUtilities = None
    pass


class MailerAzureQueueProcessor(object):

    def __init__(self, config, logger, max_num_processes=16):
        if StorageUtilities is None:
            raise Exception("Using Azure queue requires package c7n_azure to be installed.")

        self.max_num_processes = max_num_processes
        self.config = config
        self.logger = logger
        self.receive_queue = self.config['queue_url']
        self.batch_size = 16
        self.max_message_retry = 3

    def run(self, parallel=False):
        if parallel:
            self.logger.info("Parallel processing with Azure Queue is not yet implemented.")

        self.logger.info("Downloading messages from the Azure Storage queue.")
        queue_settings = StorageUtilities.get_queue_client_by_uri(self.receive_queue)
        queue_messages = StorageUtilities.get_queue_messages(
            *queue_settings, num_messages=self.batch_size)

        while len(queue_messages) > 0:
            for queue_message in queue_messages:
                self.logger.debug("Message id: %s received" % queue_message.id)

                if (self.process_azure_queue_message(queue_message) or
                        queue_message.dequeue_count > self.max_message_retry):
                    # If message handled successfully or max retry hit, delete
                    StorageUtilities.delete_queue_message(*queue_settings, message=queue_message)

            queue_messages = StorageUtilities.get_queue_messages(
                *queue_settings, num_messages=self.batch_size)

        self.logger.info('No messages left on the azure storage queue, exiting c7n_mailer.')

    def process_azure_queue_message(self, encoded_azure_queue_message):
        queue_message = json.loads(
            zlib.decompress(base64.b64decode(encoded_azure_queue_message.content)))

        self.logger.debug("Got account:%s message:%s %s:%d policy:%s recipients:%s" % (
            queue_message.get('account', 'na'),
            encoded_azure_queue_message.id,
            queue_message['policy']['resource'],
            len(queue_message['resources']),
            queue_message['policy']['name'],
            ', '.join(queue_message['action'].get('to'))))

        # this section sends a notification to the resource owner via SendGrid
        try:
            sendgrid_delivery = SendGridDelivery(self.config, self.logger)
            sendgrid_messages = sendgrid_delivery.get_to_addrs_sendgrid_messages_map(queue_message)
            return sendgrid_delivery.sendgrid_handler(queue_message, sendgrid_messages)
        except Exception:
            traceback.print_exc()
