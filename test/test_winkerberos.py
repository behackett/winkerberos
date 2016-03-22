# Copyright 2016 MongoDB, Inc.
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

import os
import sys

if sys.version_info[:2] == (2, 6):
    import unittest2 as unittest
else:
    import unittest

sys.path[0:0] = [""]

import winkerberos as kerberos

_HAVE_PYMONGO = True
try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure
except ImportError:
    _HAVE_PYMONGO = False


_HOST = os.environ.get('MONGODB_HOST', 'localhost')
_PORT = int(os.environ.get('MONGODB_PORT', 27017))
_SPN = os.environ.get('KERBEROS_SERVICE')
_PRINCIPAL = os.environ.get('KERBEROS_PRINCIPAL')
_UPN = os.environ.get('KERBEROS_UPN')
_USER = os.environ.get('KERBEROS_USER')
_DOMAIN = os.environ.get('KERBEROS_DOMAIN')
_PASSWORD = os.environ.get('KERBEROS_PASSWORD')


class TestWinKerberos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not _HAVE_PYMONGO:
            raise unittest.SkipTest("Could not import pymongo")
        if _SPN is None:
            raise unittest.SkipTest("KERBEROS_SERVICE is required")
        cls.client = MongoClient(_HOST, _PORT, connect=False, maxPoolSize=1)
        cls.db = cls.client['$external']
        try:
            cls.client.admin.command('ismaster')
        except ConnectionFailure:
            raise unittest.SkipTest("Could not connection to MongoDB")

    def test_authenticate(self):
        res, ctx = kerberos.authGSSClientInit(
            _SPN,
            _PRINCIPAL,
            kerberos.GSS_C_MUTUAL_FLAG,
            _USER,
            _DOMAIN,
            _PASSWORD)
        self.assertEqual(res, kerberos.AUTH_GSS_COMPLETE)

        res = kerberos.authGSSClientStep(ctx, "")
        self.assertEqual(res, kerberos.AUTH_GSS_CONTINUE)

        payload = kerberos.authGSSClientResponse(ctx)
        self.assertIsInstance(payload, str)

        response = self.db.command(
            'saslStart', mechanism='GSSAPI', payload=payload)
        while res == kerberos.AUTH_GSS_CONTINUE:
            res = kerberos.authGSSClientStep(ctx, response['payload'])
            payload = kerberos.authGSSClientResponse(ctx) or ''
            response = self.db.command(
               'saslContinue',
               conversationId=response['conversationId'],
               payload=payload)

        res = kerberos.authGSSClientUnwrap(ctx, response['payload'])
        self.assertEqual(res, 1)

        unwrapped = kerberos.authGSSClientResponse(ctx)
        self.assertIsInstance(unwrapped, str)

        # Try just rewrapping (no user)
        res = kerberos.authGSSClientWrap(ctx, unwrapped)
        self.assertEqual(res, 1)

        wrapped = kerberos.authGSSClientResponse(ctx)
        self.assertIsInstance(wrapped, str)

        # Actually complete authentication
        res = kerberos.authGSSClientWrap(ctx, unwrapped, _UPN)
        self.assertEqual(res, 1)

        wrapped = kerberos.authGSSClientResponse(ctx)
        self.assertIsInstance(wrapped, str)

        response = self.db.command(
           'saslContinue',
           conversationId=response['conversationId'],
           payload=wrapped)
        self.assertTrue(response['done'])

        self.assertIsInstance(kerberos.authGSSClientUsername(ctx), str)

    def test_uninitialized_context(self):
        res, ctx = kerberos.authGSSClientInit(
            _SPN,
            _PRINCIPAL,
            kerberos.GSS_C_MUTUAL_FLAG,
            _USER,
            _DOMAIN,
            _PASSWORD)
        self.assertEqual(res, kerberos.AUTH_GSS_COMPLETE)

        self.assertIsNone(kerberos.authGSSClientResponse(ctx))
        self.assertIsNone(kerberos.authGSSClientUsername(ctx))
        self.assertRaises(
            kerberos.KrbError, kerberos.authGSSClientUnwrap, ctx, "foobar")
        self.assertRaises(
            kerberos.KrbError, kerberos.authGSSClientWrap, ctx, "foobar")
