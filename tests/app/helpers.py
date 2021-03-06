# -*- coding: utf-8 -*-
import re
from mock import patch
from app import create_app
from tests import login_for_tests
from werkzeug.http import parse_cookie
from app import data_api_client
from datetime import datetime, timedelta
from dmutils.formats import DATETIME_FORMAT
import pytest


# intended to be used as a mock's side_effect
def assert_args_and_raise(e, *args, **kwargs):
    def _inner(*inner_args, **inner_kwargs):
        assert args == inner_args
        assert kwargs == inner_kwargs
        raise e
    return _inner


# intended to be used as a mock's side_effect
def assert_args_and_return(retval, *args, **kwargs):
    def _inner(*inner_args, **inner_kwargs):
        assert args == inner_args
        assert kwargs == inner_kwargs
        return retval
    return _inner


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
    "SQ1-1a": "Legal Supplier Name",
    "SQ1-1b": "Blah",
    "SQ1-1cii": "Blah",
    "SQ1-1d": "Blah",
    "SQ1-1d-i": "Blah",
    "SQ1-1d-ii": "Blah",
    "SQ1-1e": "Blah",
    "SQ1-1h": "999999999",
    "SQ1-1i-ii": "Blah",
    "SQ1-1j-ii": "Blah",
    "SQ1-1k": "Blah",
    "SQ1-1n": "Blah",
    "SQ1-1o": "Blah@example.com",
    "SQ1-2a": "Blah",
    "SQ1-2b": "Blah@example.com",
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


# a lambda so we can be sure we get a fresh copy every time. missing "status" field.
def valid_g9_declaration_base():
    return {
        "unfairCompetition": False,
        "skillsAndResources": False,
        "offerServicesYourselves": False,
        "fullAccountability": True,
        "termsOfParticipation": True,
        "termsAndConditions": True,
        "canProvideFromDayOne": True,
        "10WorkingDays": True,
        "MI": True,
        "conspiracy": False,
        "corruptionBribery": True,
        "fraudAndTheft": False,
        "terrorism": True,
        "organisedCrime": False,
        "taxEvasion": False,
        "environmentalSocialLabourLaw": False,
        "bankrupt": False,
        "graveProfessionalMisconduct": False,
        "distortingCompetition": False,
        "conflictOfInterest": False,
        "distortedCompetition": True,
        "significantOrPersistentDeficiencies": True,
        "seriousMisrepresentation": True,
        "witheldSupportingDocuments": True,
        "influencedContractingAuthority": True,
        "confidentialInformation": True,
        "misleadingInformation": True,
        "mitigatingFactors": "Money is no object",
        "unspentTaxConvictions": True,
        "GAAR": True,
        "mitigatingFactors2": "Project favourably entertained by auditors",
        "environmentallyFriendly": False,
        "equalityAndDiversity": False,
        "employersInsurance": u"Not applicable - your organisation does not need employer’s liability "
                              "insurance because your organisation employs only the owner or close family members. ",
        "publishContracts": False,
        "readUnderstoodGuidance": True,
        "understandTool": True,
        "understandHowToAskQuestions": True,
        "accurateInformation": True,
        "informationChanges": True,
        "accuratelyDescribed": True,
        "proofOfClaims": True,
        "nameOfOrganisation": "Mr Malachi Mulligan. Fertiliser and Incubator.",
        "tradingNames": "Omphalos dutiful yeoman services",
        "registeredAddressBuilding": "Omphalos",
        "registeredAddressTown": "Lambay Island",
        "registeredAddressPostcode": "N/A",
        "firstRegistered": "5/6/1904",
        "currentRegisteredCountry": u"Éire",
        "companyRegistrationNumber": "00000014",
        "dunsNumber": "987654321",
        "registeredVATNumber": "123456789",
        "establishedInTheUK": False,
        "appropriateTradeRegisters": True,
        "appropriateTradeRegistersNumber": "242#353",
        "licenceOrMemberRequired": "none of the above",
        "licenceOrMemberRequiredDetails": "",
        "subcontracting": [
            "yourself without the use of third parties (subcontractors)",
        ],
        "organisationSize": "small",
        "tradingStatus": "other (please specify)",
        "tradingStatusOther": "Proposed",
        "primaryContact": "B. Mulligan",
        "primaryContactEmail": "buck@example.com",
        "contactNameContractNotice": "Malachi Mulligan",
        "contactEmailContractNotice": "malachi@example.com",
        "servicesHaveOrSupport": True,
        "servicesDoNotInclude": True,
        "payForWhatUse": True,
        "helpBuyersComplyTechnologyCodesOfPractice": True
    }


def empty_g7_draft_service():
    return {
        'id': 1,
        'supplierId': 1234,
        'supplierName': 'supplierName',
        'frameworkName': 'G-Cloud 7',
        'frameworkSlug': 'g-cloud-7',
        'lot': 'scs',
        'lotSlug': 'scs',
        'lotName': 'Specialist Cloud Services',
        'status': 'not-submitted',
        'links': {},
        'updatedAt': '2015-06-29T15:26:07.650368Z',
    }


def empty_g9_draft_service():
    return {
        'id': 1,
        'supplierId': 1234,
        'supplierName': 'supplierName',
        'frameworkName': 'G-Cloud 9',
        'frameworkSlug': 'g-cloud-9',
        'lot': 'cloud-hosting',
        'lotSlug': 'cloud-hosting',
        'lotName': 'Cloud hosting',
        'status': 'not-submitted',
        'links': {},
        'updatedAt': '2017-02-01T15:26:07.650368Z',
    }


class BaseApplicationTest(object):
    def setup_method(self, method):
        self.app = create_app('test')
        self.app.register_blueprint(login_for_tests)
        self.client = self.app.test_client()
        self.get_user_patch = None

    def teardown_method(self, method):
        self.teardown_login()

    @staticmethod
    def get_cookie_by_name(response, name):
        cookies = response.headers.getlist('Set-Cookie')
        for cookie in cookies:
            if name in parse_cookie(cookie):
                return parse_cookie(cookie)
        return None

    @staticmethod
    def supplier():
        return {
            "suppliers": {
                "id": 12345,
                "name": "Supplier Name",
                'description': 'Supplier Description',
                'dunsNumber': '999999999',
                'companiesHouseId': 'SC009988',
                'contactInformation': [{
                    'id': 1234,
                    'contactName': 'contact name',
                    'phoneNumber': '099887',
                    'email': 'email@email.com',
                    'website': 'http://myweb.com',
                }],
                'clients': ['one client', 'two clients']
            }
        }

    @staticmethod
    def user(id, email_address, supplier_id, supplier_name, name,
             is_token_valid=True, locked=False, active=True, role='buyer'):

        hours_offset = -1 if is_token_valid else 1
        date = datetime.utcnow() + timedelta(hours=hours_offset)
        password_changed_at = date.strftime(DATETIME_FORMAT)

        user = {
            "id": id,
            "emailAddress": email_address,
            "name": name,
            "role": role,
            "locked": locked,
            'active': active,
            'passwordChangedAt': password_changed_at
        }

        if supplier_id:
            supplier = {
                "supplierId": supplier_id,
                "name": supplier_name,
            }
            user['role'] = 'supplier'
            user['supplier'] = supplier
        return {
            "users": user
        }

    @staticmethod
    def strip_all_whitespace(content):
        pattern = re.compile(r'\s+')
        return re.sub(pattern, '', content)

    @staticmethod
    def services():
        return {
            'services': [
                {
                    'id': 'id',
                    'serviceName': 'serviceName',
                    'frameworkName': 'frameworkName',
                    'lot': 'lot',
                    'serviceSummary': 'serviceSummary'
                }
            ]
        }

    @staticmethod
    def framework(
            status='open',
            name='G-Cloud 7',
            slug='g-cloud-7',
            clarification_questions_open=True,
            framework_agreement_version=None
    ):
        if 'g-cloud-' in slug:
            if slug == 'g-cloud-9':
                lots = [
                    {'id': 1, 'slug': 'cloud-hosting', 'name': 'Cloud hosting', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 2, 'slug': 'cloud-software', 'name': 'Cloud software', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 3, 'slug': 'cloud-support', 'name': 'Cloud support', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                ]
            else:
                lots = [
                    {'id': 1, 'slug': 'iaas', 'name': 'Infrastructure as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 2, 'slug': 'scs', 'name': 'Specialist Cloud Services', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 3, 'slug': 'paas', 'name': 'Platform as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 4, 'slug': 'saas', 'name': 'Software as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                ]
            metaframework = "g-cloud"
        elif 'digital-outcomes-and-specialists' in slug:
            lots = [
                {'id': 1, 'slug': 'digital-specialists', 'name': 'Digital specialists', 'oneServiceLimit': True,
                 'unitSingular': 'service', 'unitPlural': 'service'},
            ]
            metaframework = "digital-outcomes-and-specialists"

        return {
            'frameworks': {
                'status': status,
                'clarificationQuestionsOpen': clarification_questions_open,
                'name': name,
                'slug': slug,
                'lots': lots,
                'frameworkAgreementVersion': framework_agreement_version,
                'framework': metaframework,
            }
        }

    @staticmethod
    def supplier_framework(
        supplier_id=1234,
        framework_slug=None,
        declaration='default',
        status=None,
        on_framework=False,
        agreement_returned=False,
        agreement_returned_at=None,
        agreement_details=None,
        agreement_path=None,
        countersigned=False,
        countersigned_at=None,
        countersigned_details=None,
        countersigned_path=None,
        agreed_variations={},
        agreement_id=None,
        prefill_declaration_from_framework_slug=None,
    ):
        if declaration == 'default':
            declaration = FULL_G7_SUBMISSION.copy()
        if status is not None:
            declaration['status'] = status
        return {
            'frameworkInterest': {
                'supplierId': supplier_id,
                'frameworkSlug': framework_slug,
                'declaration': declaration,
                'onFramework': on_framework,
                'agreementReturned': agreement_returned,
                'agreementReturnedAt': agreement_returned_at,
                'agreementDetails': agreement_details,
                'agreementPath': agreement_path,
                'countersigned': countersigned,
                'countersignedAt': countersigned_at,
                'countersignedDetails': countersigned_details,
                'countersignedPath': countersigned_path,
                'agreementId': agreement_id,
                'agreedVariations': agreed_variations,
                'prefillDeclarationFromFrameworkSlug': prefill_declaration_from_framework_slug,
            }
        }

    @staticmethod
    def framework_agreement(
            id=234,
            supplier_id=1234,
            framework_slug="g-cloud-8",
            signed_agreement_details=None,
            signed_agreement_path=None
    ):
        return {
            "agreement": {
                "id": id,
                "supplierId": supplier_id,
                "frameworkSlug": framework_slug,
                "signedAgreementDetails": signed_agreement_details,
                "signedAgreementPath": signed_agreement_path
            }
        }

    @staticmethod
    def brief_response(
            id=5,
            brief_id=1234,
            supplier_id=1234,
            data=None
    ):
        result = {
            "briefResponses": {
                "id": id,
                "briefId": brief_id,
                "supplierId": supplier_id
            }
        }

        if data:
            result['briefResponses'].update(data)

        return result

    def teardown_login(self):
        if self.get_user_patch is not None:
            self.get_user_patch.stop()

    def login(self):
        with patch('app.main.views.login.data_api_client') as login_api_client:
            login_api_client.authenticate_user.return_value = self.user(
                123, "email@email.com", 1234, u'Supplier NĀme', u'Năme')

            self.get_user_patch = patch.object(
                data_api_client,
                'get_user',
                return_value=self.user(123, "email@email.com", 1234, u'Supplier NĀme', u'Năme')
            )
            self.get_user_patch.start()

            response = self.client.get("/auto-login")
            assert response.status_code == 200

    def login_as_buyer(self):
        with patch('app.main.views.login.data_api_client') as login_api_client:

            login_api_client.authenticate_user.return_value = self.user(
                234, "buyer@email.com", None, None, 'Ā Buyer', role='buyer')

            self.get_user_patch = patch.object(
                data_api_client,
                'get_user',
                return_value=self.user(234, "buyer@email.com", None, None, 'Buyer', role='buyer')
            )
            self.get_user_patch.start()

            response = self.client.get("/auto-buyer-login")
            assert response.status_code == 200

    def assert_in_strip_whitespace(self, needle, haystack):
        assert self.strip_all_whitespace(needle) in self.strip_all_whitespace(haystack)

    def assert_not_in_strip_whitespace(self, needle, haystack):
        assert self.strip_all_whitespace(needle) not in self.strip_all_whitespace(haystack)

    # Method to test flashes taken from http://blog.paulopoiati.com/2013/02/22/testing-flash-messages-in-flask/
    def assert_flashes(self, expected_message, expected_category='message'):
        with self.client.session_transaction() as session:
            try:
                category, message = session['_flashes'][0]
            except KeyError:
                raise AssertionError('nothing flashed')
            try:
                assert expected_message == message or expected_message in message
            except TypeError:
                # presumably this was raised from the "in" test being reached and fed types which don't support "in".
                # either way, a failure.
                pytest.fail("Flash message contents not found in _flashes")
            assert expected_category == category

    def assert_no_flashes(self):
        with self.client.session_transaction() as session:
            assert not session.get("_flashes")


class FakeMail(object):
    """An object that equals strings containing all of the given substrings

    Can be used in mock.call comparisons (eg to verify email templates).

    """
    def __init__(self, *substrings):
        self.substrings = substrings

    def __eq__(self, other):
        return all(substring in other for substring in self.substrings)

    def __repr__(self):
        return "<FakeMail: {}>".format(self.substrings)
