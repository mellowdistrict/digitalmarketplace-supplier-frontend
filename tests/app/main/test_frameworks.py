# -*- coding: utf-8 -*-
from nose.tools import assert_equal, assert_true, assert_in, assert_not_in
import os
import mock
from lxml import html
from dmutils.apiclient import APIError
from dmutils.audit import AuditTypes
from dmutils.email import MandrillException
from dmutils.s3 import S3ResponseError

from ..helpers import BaseApplicationTest


def _return_fake_s3_file_dict(directory, filename, ext, last_modified=None, size=None):

    return {
        'path': '{}{}.{}'.format(directory, filename, ext),
        'filename': filename,
        'ext': ext,
        'last_modified': last_modified or '2015-08-17T14:00:00.000Z',
        'size': size if size is not None else 1
    }


@mock.patch('dmutils.s3.S3')
@mock.patch('app.main.views.frameworks.data_api_client', autospec=True)
class TestFrameworksDashboard(BaseApplicationTest):

    @staticmethod
    def _assert_last_updated_times(doc, last_updateds):

        for last_updated in last_updateds:
            hint = doc.xpath(
                '//li[contains(@class, "framework-application-section")]'
                '//span[contains(text(), "{}")]'
                '/../..'
                '/div[@class="hint"]'.format(last_updated['text'])
            )

            if last_updated.get('time'):
                time = hint[0].find('./time')
                assert_equal(last_updated['time']['text'], time.text)
                assert_equal(last_updated['time']['datetime'], time.get('datetime'))

            else:
                assert_equal(len(hint), 0)

    def test_shows(self, data_api_client, s3):
        with self.app.test_client():
            data_api_client.get_framework.return_value = self.framework(status='open')
            self.login()

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            assert_equal(res.status_code, 200)

    def test_interest_registered_in_framework_on_post(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            res = self.client.post("/suppliers/frameworks/digital-outcomes-and-specialists")

            assert_equal(res.status_code, 200)
            data_api_client.register_framework_interest.assert_called_once_with(
                1234,
                "digital-outcomes-and-specialists",
                "email@email.com"
            )

    def test_interest_not_registered_in_framework_on_get(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            res = self.client.get("/suppliers/frameworks/digital-outcomes-and-specialists")

            assert_equal(res.status_code, 200)
            assert not data_api_client.register_framework_interest.called

    def test_shows_gcloud_7_closed_message_if_pending_and_no_application_done(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='pending')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'not-submitted'}
                ]
            }

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            doc = html.fromstring(res.get_data(as_text=True))

            heading = doc.xpath('//div[@class="summary-item-lede"]//h2[@class="summary-item-heading"]')
            assert_true(len(heading) > 0)
            assert_in(u"G-Cloud 7 is closed for applications",
                      heading[0].xpath('text()')[0])
            assert_in(u"You didn't submit an application.",
                      heading[0].xpath('../p[1]/text()')[0])

    def test_shows_gcloud_7_closed_message_if_pending_and_application(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='pending')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            doc = html.fromstring(res.get_data(as_text=True))

            heading = doc.xpath('//div[@class="summary-item-lede"]//h2[@class="summary-item-heading"]')
            assert_true(len(heading) > 0)
            assert_in(u"G-Cloud 7 is closed for applications",
                      heading[0].xpath('text()')[0])
            assert_in(u"You made your supplier declaration and submitted 1 service for consideration.",
                      heading[0].xpath('../p[1]/text()')[0])
            assert_in(u"A letter informing you whether your application was successful or not will be posted on your G-Cloud 7 updates page by Monday, 9 November 2015.",  # noqa
                      heading[0].xpath('../p[2]/text()')[0])  # noqa

    def test_declaration_status_when_complete(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            doc = html.fromstring(res.get_data(as_text=True))
            assert_equal(
                len(doc.xpath(u'//p/strong[contains(text(), "You’ve made the supplier declaration")]')),
                1)

    def test_declaration_status_when_started(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            submission = FULL_G7_SUBMISSION.copy()
            # User has not yet submitted page 3 of the declaration
            del submission['SQ2-1abcd']
            del submission['SQ2-1e']
            del submission['SQ2-1f']
            del submission['SQ2-1ghijklmn']
            submission.update({"status": "started"})

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": submission}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            doc = html.fromstring(res.get_data(as_text=True))
            assert_equal(
                len(doc.xpath('//p[contains(text(), "You need to finish making the supplier declaration")]')),  # noqa
                1)

    def test_declaration_status_when_not_complete(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_framework_info.side_effect = APIError(mock.Mock(status_code=404))

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            doc = html.fromstring(res.get_data(as_text=True))
            assert_equal(
                len(doc.xpath('//p[contains(text(), "You need to make the supplier declaration")]')),
                1)

    def test_last_updated_exists_for_both_sections(self, data_api_client, s3):
        files = [
            ('g-cloud-7-updates/communications/', 'file 1', 'odt', '2015-01-01T14:00:00.000Z'),
            ('g-cloud-7-updates/clarifications/', 'file 2', 'odt', '2015-02-02T14:00:00.000Z'),
            ('', 'g-cloud-7-supplier-pack', 'zip', '2015-01-01T14:00:00.000Z'),
        ]

        s3.return_value.list.return_value = [
            _return_fake_s3_file_dict(section, filename, ext, last_modified=last_modified)
            for section, filename, ext, last_modified in files
        ]

        with self.app.test_client():
            self.login()

            res = self.client.get("/suppliers/frameworks/g-cloud-7")
            doc = html.fromstring(res.get_data(as_text=True))
            last_updateds = [
                {
                    'text': "Download guidance and legal documentation (.zip)",
                    'time': {
                        'text': 'Thursday 01 January 2015',
                        'datetime': '2015-01-01T14:00:00.000Z'
                    }
                },
                {
                    'text': "Read updates and ask clarification questions",
                    'time': {
                        'text': 'Monday 02 February 2015',
                        'datetime': '2015-02-02T14:00:00.000Z'
                    }
                }
            ]

            self._assert_last_updated_times(doc, last_updateds)

    def test_last_updated_exists_for_one_section(self, data_api_client, s3):
        files = [
            ('', 'g-cloud-7-supplier-pack', 'zip', '2015-01-01T14:00:00.000Z'),
        ]

        s3.return_value.list.return_value = [
            _return_fake_s3_file_dict(section, filename, ext, last_modified=last_modified)
            for section, filename, ext, last_modified in files
        ]

        with self.app.test_client():
            self.login()

            res = self.client.get("/suppliers/frameworks/g-cloud-7")
            doc = html.fromstring(res.get_data(as_text=True))
            last_updateds = [
                {
                    'text': "Download guidance and legal documentation (.zip)",
                    'time': {
                        'text': 'Thursday 01 January 2015',
                        'datetime': '2015-01-01T14:00:00.000Z'
                    }
                },
                {
                    'text': "Read updates and ask clarification questions"
                }
            ]

            self._assert_last_updated_times(doc, last_updateds)

    def test_last_updated_does_not_exist(self, data_api_client, s3):
        s3.return_value.list.return_value = []

        with self.app.test_client():
            self.login()

            res = self.client.get("/suppliers/frameworks/g-cloud-7")
            doc = html.fromstring(res.get_data(as_text=True))
            last_updateds = [
                {'text': "Download guidance and legal documentation (.zip)"},
                {'text': "Read updates and ask clarification questions"}
            ]

            self._assert_last_updated_times(doc, last_updateds)

    def test_returns_404_if_framework_does_not_exist(self, data_api_client, s3):
        with self.app.test_client():
            self.login()
            data_api_client.get_framework.return_value = {'frameworks': {}}

            res = self.client.get('/suppliers/frameworks/does-not-exist')

            assert_equal(res.status_code, 404)

    def test_result_letter_is_shown_when_is_in_standstill(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            data = res.get_data(as_text=True)

            assert_in(u'Download your application result letter', data)

    def test_result_letter_is_not_shown_when_not_in_standstill(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='pending')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            data = res.get_data(as_text=True)

            assert_not_in(u'Download your application result letter', data)

    def test_result_letter_is_not_shown_when_no_application(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'not-submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            data = res.get_data(as_text=True)

            assert_not_in(u'Download your application result letter', data)

    def test_link_to_framework_agreement_is_shown_if_supplier_is_on_framework(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION, "onFramework": True}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            data = res.get_data(as_text=True)

            assert_in(u'Sign and return your framework agreement', data)

    def test_link_to_framework_agreement_is_shown_if_supplier_is_not_on_framework(self, data_api_client, s3):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_framework_interest.return_value = {'frameworks': ['g-cloud-7']}
            data_api_client.find_draft_services.return_value = {
                "services": [
                    {'serviceName': 'A service', 'status': 'submitted'}
                ]
            }
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION, "onFramework": False}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7")

            data = res.get_data(as_text=True)

            assert_not_in(u'Sign and return your framework agreement', data)


@mock.patch('app.main.views.frameworks.data_api_client', autospec=True)
class TestFrameworkAgreement(BaseApplicationTest):
    def test_page_renders_if_all_ok(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION, "onFramework": True}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7/agreement")

            assert_equal(res.status_code, 200)

    def test_page_returns_404_if_framework_in_wrong_state(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION, "onFramework": True}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7/agreement")

            assert_equal(res.status_code, 404)

    def test_page_returns_404_if_supplier_not_on_framework(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='standstill')
            data_api_client.get_supplier_framework_info.return_value = {
                "frameworkInterest": {
                    "declaration": FULL_G7_SUBMISSION, "onFramework": False}}

            res = self.client.get("/suppliers/frameworks/g-cloud-7/agreement")

            assert_equal(res.status_code, 404)


@mock.patch('dmutils.s3.S3')
class TestFrameworkAgreementDocumentDownload(BaseApplicationTest):
    def test_download_document(self, S3):
        uploader = mock.Mock()
        S3.return_value = uploader
        uploader.get_signed_url.return_value = 'http://url/path?param=value'

        with self.app.test_client():
            self.login()

            res = self.client.get('/suppliers/frameworks/g-cloud-7/agreements/example.pdf')

            assert_equal(res.status_code, 302)
            assert_equal(res.location, 'http://url/path?param=value')
            uploader.get_signed_url.assert_called_with('g-cloud-7/agreements/1234/1234-example.pdf')

    def test_download_document_with_asset_url(self, S3):
        uploader = mock.Mock()
        S3.return_value = uploader
        uploader.get_signed_url.return_value = 'http://url/path?param=value'

        with self.app.test_client():
            self.app.config['DM_ASSETS_URL'] = 'https://example'
            self.login()

            res = self.client.get('/suppliers/frameworks/g-cloud-7/agreements/example.pdf')

            assert_equal(res.status_code, 302)
            assert_equal(res.location, 'https://example/path?param=value')
            uploader.get_signed_url.assert_called_with('g-cloud-7/agreements/1234/1234-example.pdf')


@mock.patch('dmutils.s3.S3')
class TestFrameworkDocumentDownload(BaseApplicationTest):
    def test_download_document(self, S3):
        uploader = mock.Mock()
        S3.return_value = uploader
        uploader.get_signed_url.return_value = 'http://url/path?param=value'

        with self.app.test_client():
            self.login()

            res = self.client.get('/suppliers/frameworks/g-cloud-7/files/example.pdf')

            assert_equal(res.status_code, 302)
            assert_equal(res.location, 'http://localhost/path?param=value')
            uploader.get_signed_url.assert_called_with('example.pdf')

    def test_download_document_returns_404_if_url_is_None(self, S3):
        uploader = mock.Mock()
        S3.return_value = uploader
        uploader.get_signed_url.return_value = None

        with self.app.test_client():
            self.login()

            res = self.client.get('/suppliers/frameworks/g-cloud-7/files/example.pdf')

            assert_equal(res.status_code, 404)

    def test_redirect_g7_document_downloads(self, s3):

        for filename in ['foo.pdf', 'foo.zip', 'foo/bar.pdf']:
            with self.app.test_client():
                self.login()

                res = self.client.get('/suppliers/frameworks/g-cloud-7/{}'.format(filename))

                assert_equal(res.status_code, 301)
                assert_equal(res.location,
                             'http://localhost/suppliers/frameworks/g-cloud-7/files/{}'.format(filename))


FULL_G7_SUBMISSION = {
    "status": "complete",
    "PR1": "true",
    "PR2": "true",
    "PR3": "true",
    "PR4": "true",
    "PR5": "true",
    "SQ1-1i-i": "true",
    "SQ2-1abcd": "true",
    "SQ2-1e": "true",
    "SQ2-1f": "true",
    "SQ2-1ghijklmn": "true",
    "SQ2-2a": "true",
    "SQ3-1a": "true",
    "SQ3-1b": "true",
    "SQ3-1c": "true",
    "SQ3-1d": "true",
    "SQ3-1e": "true",
    "SQ3-1f": "true",
    "SQ3-1g": "true",
    "SQ3-1h-i": "true",
    "SQ3-1h-ii": "true",
    "SQ3-1i-i": "true",
    "SQ3-1i-ii": "true",
    "SQ3-1j": "true",
    "SQ3-1k": "Blah",
    "SQ4-1a": "true",
    "SQ4-1b": "true",
    "SQ5-2a": "true",
    "SQD2b": "true",
    "SQD2d": "true",
    "SQ1-1a": "Blah",
    "SQ1-1b": "Blah",
    "SQ1-1cii": "Blah",
    "SQ1-1d": "Blah",
    "SQ1-1e": "Blah",
    "SQ1-1h": "999999999",
    "SQ1-1i-ii": "Blah",
    "SQ1-1j-ii": "Blah",
    "SQ1-1k": "Blah",
    "SQ1-1n": "Blah",
    "SQ1-1o": "Blah",
    "SQ1-2a": "Blah",
    "SQ1-2b": "Blah",
    "SQ2-2b": "Blah",
    "SQ4-1c": "Blah",
    "SQD2c": "Blah",
    "SQD2e": "Blah",
    "SQ1-1ci": "public limited company",
    "SQ1-1j-i": "licensed?",
    "SQ1-1m": "micro",
    "SQ1-3": "on-demand self-service. blah blah",
    "SQ5-1a": u"Yes – your organisation has, blah blah",
    "SQC2": [
        "race?",
        "sexual orientation?",
        "disability?",
        "age equality?",
        "religion or belief?",
        "gender (sex)?",
        "gender reassignment?",
        "marriage or civil partnership?",
        "pregnancy or maternity?",
        "human rights?"
    ],
    "SQC3": "true",
    "SQA2": "true",
    "SQA3": "true",
    "SQA4": "true",
    "SQA5": "true",
    "AQA3": "true",
    "SQE2a": ["as a prime contractor, using third parties (subcontractors) to provide some services"]
}


@mock.patch('app.main.views.frameworks.data_api_client', autospec=True)
class TestSupplierDeclaration(BaseApplicationTest):
    def test_get_with_no_previous_answers(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_declaration.side_effect = APIError(mock.Mock(status_code=404))

            res = self.client.get(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials')

            assert_equal(res.status_code, 200)
            doc = html.fromstring(res.get_data(as_text=True))
            assert_equal(
                doc.xpath('//input[@id="PR-1-yes"]/@checked'), [])
            assert_equal(
                doc.xpath('//input[@id="PR-1-no"]/@checked'), [])

    def test_get_with_with_previous_answers(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_declaration.return_value = {
                "declaration": {"status": "started", "PR1": False}
            }

            res = self.client.get(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials')

            assert_equal(res.status_code, 200)
            doc = html.fromstring(res.get_data(as_text=True))
            assert_equal(
                len(doc.xpath('//input[@id="input-PR1-no"]/@checked')), 1)

    def test_post_valid_data(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_declaration.return_value = {
                "declaration": {"status": "started"}
            }
            res = self.client.post(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials',
                data=FULL_G7_SUBMISSION)

            assert_equal(res.status_code, 302)
            assert data_api_client.set_supplier_declaration.called

    def test_post_valid_data_to_complete_declaration(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_declaration.return_value = {
                "declaration": {"status": "started"}
            }
            res = self.client.post(
                '/suppliers/frameworks/g-cloud-7/declaration/grounds_for_discretionary_exclusion',
                data=FULL_G7_SUBMISSION)

            assert_equal(res.status_code, 302)
            assert_equal(res.location, 'http://localhost/suppliers/frameworks/g-cloud-7?declaration_completed=true')
            assert data_api_client.set_supplier_declaration.called

    def test_post_valid_data_with_api_failure(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            data_api_client.get_supplier_declaration.return_value = {
                "declaration": {"status": "started"}
            }
            data_api_client.set_supplier_declaration.side_effect = APIError(mock.Mock(status_code=400))

            res = self.client.post(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials',
                data=FULL_G7_SUBMISSION)

            assert_equal(res.status_code, 400)

    @mock.patch('app.main.views.frameworks.get_error_messages_for_page')
    def test_post_with_validation_errors(self, get_error_messages_for_page, data_api_client):
        """Test that answers are not saved if there are errors

        For unit tests of the validation see :mod:`tests.app.main.helpers.test_frameworks`
        """
        with self.app.test_client():
            self.login()

            data_api_client.get_framework.return_value = self.framework(status='open')
            get_error_messages_for_page.return_value = {'PR1': {'input_name': 'PR1', 'message': 'this is invalid'}}

            res = self.client.post(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials',
                data=FULL_G7_SUBMISSION)

            assert_equal(res.status_code, 400)
            assert not data_api_client.set_supplier_declaration.called

    def test_cannot_post_data_if_not_open(self, data_api_client):
        with self.app.test_client():
            self.login()

            data_api_client.get_framework_status.return_value = {'status': 'other'}
            data_api_client.get_supplier_declaration.return_value = {
                "declaration": {"status": "started"}
            }
            res = self.client.post(
                '/suppliers/frameworks/g-cloud-7/declaration/g_cloud_7_essentials',
                data=FULL_G7_SUBMISSION)

            assert_equal(res.status_code, 404)
            assert not data_api_client.set_supplier_declaration.called


@mock.patch('app.main.views.frameworks.data_api_client')
@mock.patch('dmutils.s3.S3')
class TestFrameworkUpdatesPage(BaseApplicationTest):

    def _assert_page_title_and_table_headings(self, doc, tables_exist=True):

        assert_true(
            self.strip_all_whitespace('G-Cloud 7 updates')
            in self.strip_all_whitespace(doc.xpath('//h1')[0].text)
        )

        section_names = [
            'G-Cloud 7 communications',
            'G-Cloud 7 clarification questions and answers',
        ]

        headers = doc.xpath('//div[contains(@class, "updates-document-tables")]/h2[@class="summary-item-heading"]')
        assert_equal(len(headers), 2)
        for index, section_name in enumerate(section_names):
            assert_true(
                self.strip_all_whitespace(section_name)
                in self.strip_all_whitespace(headers[index].text)
            )

        if tables_exist:
            table_captions = doc.xpath('//div[contains(@class, "updates-document-tables")]/table/caption')
            assert_equal(len(table_captions), 2)
            for index, section_name in enumerate(section_names):
                assert_true(
                    self.strip_all_whitespace(section_name)
                    in self.strip_all_whitespace(table_captions[index].text)
                )

    def test_should_be_a_503_if_connecting_to_amazon_fails(self, s3, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')
        # if s3 throws a 500-level error
        s3.side_effect = S3ResponseError(500, 'Amazon has collapsed. The internet is over.')

        with self.app.test_client():
            self.login()

            response = self.client.get(
                '/suppliers/frameworks/g-cloud-7/updates'
            )

            assert_equal(response.status_code, 503)
            assert_true(
                self.strip_all_whitespace("<h1>Sorry, we're experiencing technical difficulties</h1>")
                in self.strip_all_whitespace(response.get_data(as_text=True))
            )

    def test_empty_messages_exist_if_no_files_returned(self, s3, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')

        with self.app.test_client():
            self.login()

            response = self.client.get(
                '/suppliers/frameworks/g-cloud-7/updates'
            )

            assert_equal(response.status_code, 200)
            doc = html.fromstring(response.get_data(as_text=True))
            self._assert_page_title_and_table_headings(doc, tables_exist=False)

            for empty_message in [
                '<p class="summary-item-no-content">No communications have been sent out</p>',
                '<p class="summary-item-no-content">No clarification questions and answers  have been posted yet</p>',
            ]:
                assert_true(
                    self.strip_all_whitespace(empty_message)
                    in self.strip_all_whitespace(response.get_data(as_text=True))
                )

    def test_the_tables_should_be_displayed_correctly(self, s3, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')

        files = [
            ('g-cloud-7-updates/communications/', 'file 1', 'odt'),
            ('g-cloud-7-updates/communications/', 'file 2', 'odt'),
            ('g-cloud-7-updates/clarifications/', 'file 3', 'odt'),
            ('g-cloud-7-updates/clarifications/', 'file 4', 'odt'),
        ]

        # the communications table is always before the clarifications table
        s3.return_value.list.return_value = [
            _return_fake_s3_file_dict(section, filename, ext) for section, filename, ext in files
        ]

        with self.app.test_client():
            self.login()

            response = self.client.get(
                '/suppliers/frameworks/g-cloud-7/updates'
            )
            doc = html.fromstring(response.get_data(as_text=True))
            self._assert_page_title_and_table_headings(doc)

            tables = doc.xpath('//div[contains(@class, "updates-document-tables")]/table')

            # test that for each table, we have the right number of rows
            for table in tables:
                item_rows = table.findall('.//tr[@class="summary-item-row"]')
                assert_equal(len(item_rows), 2)

                # test that the file names and urls are right
                for row in item_rows:
                    section, filename, ext = files.pop(0)
                    filename_link = row.find('.//a[@class="document-link-with-icon"]')

                    assert_true(filename in filename_link.text_content())
                    assert_equal(
                        filename_link.get('href'),
                        '/suppliers/frameworks/g-cloud-7/files/{}{}.{}'.format(
                            section, filename.replace(' ', '%20'), ext
                        )
                    )

    def test_names_with_the_section_name_in_them_will_display_correctly(self, s3, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')

        # for example: 'g-cloud-7-updates/clarifications/communications%20file.odf'
        files = [
            ('g-cloud-7-updates/communications/', 'clarifications file', 'odt'),
            ('g-cloud-7-updates/clarifications/', 'communications file', 'odt')
        ]

        s3.return_value.list.return_value = [
            _return_fake_s3_file_dict(section, filename, ext) for section, filename, ext in files
        ]

        with self.app.test_client():
            self.login()

            response = self.client.get(
                '/suppliers/frameworks/g-cloud-7/updates'
            )
            doc = html.fromstring(response.get_data(as_text=True))
            self._assert_page_title_and_table_headings(doc)

            tables = doc.xpath('//div[contains(@class, "updates-document-tables")]/table')

            # test that for each table, we have the right number of rows
            for table in tables:
                item_rows = table.findall('.//tr[@class="summary-item-row"]')
                assert_equal(len(item_rows), 1)

                # test that the file names and urls are right
                for row in item_rows:
                    section, filename, ext = files.pop(0)
                    filename_link = row.find('.//a[@class="document-link-with-icon"]')

                    assert_true(filename in filename_link.text_content())
                    assert_equal(
                        filename_link.get('href'),
                        '/suppliers/frameworks/g-cloud-7/files/{}{}.{}'.format(
                            section, filename.replace(' ', '%20'), ext
                        )
                    )


class TestSendClarificationQuestionEmail(BaseApplicationTest):

    def _send_email(self, clarification_question):
        with self.app.test_client():
            self.login()

            return self.client.post(
                "/suppliers/frameworks/g-cloud-7/updates",
                data={
                    'clarification_question': clarification_question,
                }
            )

    def _assert_email(self, send_email, is_called=True, succeeds=True):

        if succeeds:
            assert_equal(2, send_email.call_count)
        elif is_called:
            assert_equal(1, send_email.call_count)
        else:
            assert_equal(0, send_email.call_count)

        if is_called:
            send_email.assert_any_call(
                "digitalmarketplace@mailinator.com",
                mock.ANY,
                "MANDRILL",
                "Clarification question",
                "suppliers@digitalmarketplace.service.gov.uk",
                "G-Cloud 7 Supplier",
                ["clarification-question"]
            )
        if succeeds:
            send_email.assert_any_call(
                "email@email.com",
                mock.ANY,
                "MANDRILL",
                "Thanks for your clarification question",
                "do-not-reply@digitalmarketplace.service.gov.uk",
                "Digital Marketplace Admin",
                ["clarification-question-confirm"]
            )

    def _assert_g7_email(self, send_email, succeeds=True):

        if succeeds:
            assert_equal(1, send_email.call_count)
        else:
            assert_equal(0, send_email.call_count)

        if succeeds:
            send_email.assert_called_with(
                "digitalmarketplace@mailinator.com",
                mock.ANY,
                "MANDRILL",
                "G-Cloud 7 application question",
                "email@email.com",
                "G-Cloud 7 Supplier",
                ["g7-application-question"]
            )

    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('dmutils.s3.S3')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_not_send_email_if_invalid_clarification_question(self, send_email, s3, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')

        for invalid_clarification_question in [
            {
                'question': '',  # empty question
                'error_message': 'Question cannot be empty'
            }, {
                'question': '\t   \n\n\n',  # whitespace-only question
                'error_message': 'Question cannot be empty'
            },
            {
                'question': ('ten__chars' * 500) + '1',  # 5000+ char question
                'error_message': 'Question cannot be longer than 5000 characters'
            }
        ]:

            response = self._send_email(invalid_clarification_question['question'])
            self._assert_email(send_email, is_called=False, succeeds=False)

            assert_equal(response.status_code, 400)
            assert_true(
                self.strip_all_whitespace('There was a problem with your submitted question')
                in self.strip_all_whitespace(response.get_data(as_text=True))
            )
            assert_true(
                self.strip_all_whitespace(invalid_clarification_question['error_message'])
                in self.strip_all_whitespace(response.get_data(as_text=True))
            )

    @mock.patch('dmutils.s3.S3')
    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_call_send_email_with_correct_params(self, send_email, data_api_client, s3):

        clarification_question = 'This is a clarification question.'
        response = self._send_email(clarification_question)

        self._assert_email(send_email)

        assert_equal(response.status_code, 200)
        assert_true(
            self.strip_all_whitespace('<p class="banner-message">Your clarification question has been sent. Answers to all clarification questions will be published on this page.</p>')  # noqa
            in self.strip_all_whitespace(response.get_data(as_text=True))
        )

    @mock.patch('dmutils.s3.S3')
    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_call_send_g7_email_with_correct_params(self, send_email, data_api_client, s3):
        self.app.config['FEATURE_FLAGS_G7_CLARIFICATIONS_CLOSED'] = 1
        clarification_question = 'This is a G7 question.'
        response = self._send_email(clarification_question)

        self._assert_g7_email(send_email)

        assert_equal(response.status_code, 200)
        assert_true(
            self.strip_all_whitespace('<p class="banner-message">Your question has been sent. You\'ll get a reply from the Crown Commercial Service soon.</p>')  # noqa
            in self.strip_all_whitespace(response.get_data(as_text=True))
        )

    @mock.patch('dmutils.s3.S3')
    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_create_audit_event(self, send_email, data_api_client, s3):
        clarification_question = 'This is a clarification question'
        response = self._send_email(clarification_question)

        self._assert_email(send_email)

        assert_equal(response.status_code, 200)
        data_api_client.create_audit_event.assert_called_with(
            audit_type=AuditTypes.send_clarification_question,
            user="email@email.com",
            object_type="suppliers",
            object_id=1234,
            data={"question": clarification_question})

    @mock.patch('dmutils.s3.S3')
    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_create_g7_question_audit_event(self, send_email, data_api_client, s3):
        self.app.config['FEATURE_FLAGS_G7_CLARIFICATIONS_CLOSED'] = 1
        clarification_question = 'This is a G7 question'
        response = self._send_email(clarification_question)

        self._assert_g7_email(send_email)

        assert_equal(response.status_code, 200)
        data_api_client.create_audit_event.assert_called_with(
            audit_type=AuditTypes.send_g7_application_question,
            user="email@email.com",
            object_type="suppliers",
            object_id=1234,
            data={"question": clarification_question})

    @mock.patch('app.main.views.frameworks.data_api_client')
    @mock.patch('app.main.views.frameworks.send_email')
    def test_should_be_a_503_if_email_fails(self, send_email, data_api_client):
        data_api_client.get_framework.return_value = self.framework('open')
        send_email.side_effect = MandrillException("Arrrgh")

        clarification_question = 'This is a clarification question.'
        response = self._send_email(clarification_question)
        self._assert_email(send_email, succeeds=False)

        assert_equal(response.status_code, 503)


@mock.patch('app.main.views.frameworks.data_api_client', autospec=True)
@mock.patch('app.main.views.frameworks.count_unanswered_questions')
class TestG7ServicesList(BaseApplicationTest):

    def test_404_when_g7_pending_and_no_complete_services(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()
        data_api_client.get_framework.return_value = self.framework(status='pending')
        data_api_client.find_draft_services.return_value = {'services': []}
        count_unanswered.return_value = 0
        response = self.client.get('/suppliers/frameworks/g-cloud-7/services')
        assert_equal(response.status_code, 404)

    def test_404_when_g7_pending_and_no_declaration(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()
        data_api_client.get_framework.return_value = self.framework(status='pending')
        data_api_client.get_supplier_declaration.return_value = {
            "declaration": {"status": "started"}
        }
        response = self.client.get('/suppliers/frameworks/g-cloud-7/services')
        assert_equal(response.status_code, 404)

    def test_no_404_when_g7_open_and_no_complete_services(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()
        data_api_client.get_framework_status.return_value = {'status': 'open'}
        data_api_client.find_draft_services.return_value = {'services': []}
        count_unanswered.return_value = 0
        response = self.client.get('/suppliers/frameworks/g-cloud-7/services')
        assert_equal(response.status_code, 200)

    def test_no_404_when_g7_open_and_no_declaration(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()
        data_api_client.get_framework_status.return_value = {'status': 'open'}
        data_api_client.get_supplier_declaration.return_value = {
            "declaration": {"status": "started"}
        }
        response = self.client.get('/suppliers/frameworks/g-cloud-7/services')
        assert_equal(response.status_code, 200)

    def test_shows_g7_message_if_pending_and_application_made(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()
        data_api_client.get_framework.return_value = self.framework(status='pending')
        data_api_client.get_supplier_declaration.return_value = {'declaration': FULL_G7_SUBMISSION}  # noqa
        data_api_client.find_draft_services.return_value = {
            'services': [
                {'serviceName': 'draft', 'lot': 'SCS', 'status': 'submitted'},
            ]
        }
        count_unanswered.return_value = 0, 1

        response = self.client.get('/suppliers/frameworks/g-cloud-7/services')
        doc = html.fromstring(response.get_data(as_text=True))

        assert_equal(response.status_code, 200)
        heading = doc.xpath('//div[@class="summary-item-lede"]//h2[@class="summary-item-heading"]')
        assert_true(len(heading) > 0)
        assert_in(u"G-Cloud 7 is closed for applications",
                  heading[0].xpath('text()')[0])
        assert_in(u"You made your supplier declaration and submitted 1 complete service.",
                  heading[0].xpath('../p[1]/text()')[0])

    def test_drafts_list_progress_count(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()

        count_unanswered.return_value = 3, 1
        data_api_client.get_framework.return_value = self.framework(status='open')
        data_api_client.find_draft_services.return_value = {
            'services': [
                {'serviceName': 'draft', 'lot': 'SCS', 'status': 'not-submitted'},
            ]
        }

        res = self.client.get('/suppliers/frameworks/g-cloud-7/services')

        assert_true(u'Service can be moved to complete' not in res.get_data(as_text=True))
        assert_in(u'4 unanswered questions', res.get_data(as_text=True))

    def test_drafts_list_can_be_completed(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()

        count_unanswered.return_value = 0, 1

        data_api_client.get_framework.return_value = self.framework(status='open')
        data_api_client.find_draft_services.return_value = {
            'services': [
                {'serviceName': 'draft', 'lot': 'SCS', 'status': 'not-submitted'},
            ]
        }

        res = self.client.get('/suppliers/frameworks/g-cloud-7/services')

        assert_in(u'Service can be marked as complete', res.get_data(as_text=True))
        assert_in(u'1 optional question unanswered', res.get_data(as_text=True))

    def test_drafts_list_completed(self, count_unanswered, data_api_client):
        with self.app.test_client():
            self.login()

        count_unanswered.return_value = 0, 1

        data_api_client.find_draft_services.return_value = {
            'services': [
                {'serviceName': 'draft', 'lot': 'SCS', 'status': 'submitted'},
            ]
        }

        res = self.client.get('/suppliers/frameworks/g-cloud-7/services')

        assert_true(u'Service can be moved to complete' not in res.get_data(as_text=True))
        assert_in(u'1 optional question unanswered', res.get_data(as_text=True))
