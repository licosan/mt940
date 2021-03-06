# vim: fileencoding=utf-8:
'''

Format
---------------------

Sources:

.. _Swift for corporates: http://www.sepaforcorporates.com/\
    swift-for-corporates/account-statement-mt940-file-format-overview/
.. _Rabobank MT940: https://www.rabobank.nl/images/\
    formaatbeschrijving_swift_bt940s_1_0_nl_rib_29539296.pdf

 - `Swift for corporates`_
 - `Rabobank MT940`_

::

    [] = optional
    ! = fixed length
    a = Text
    x = Alphanumeric, seems more like text actually. Can include special
        characters (slashes) and whitespace as well as letters and numbers
    d = Numeric separated by decimal (usually comma)
    c = Code list value
    n = Numeric
'''
import re
import logging

try:
    import enum
except ImportError:  # pragma: no cover
    import sys
    print >> sys.stderr, 'MT940 requires the `enum34` package'

    class enum(object):
        @staticmethod
        def unique(*args, **kwargs):
            return []

        Enum = object

from . import models


logger = logging.getLogger(__name__)


class Tag(object):
    id = 0
    scope = models.Transactions

    def __init__(self):
        self.re = re.compile(self.pattern,
                             re.IGNORECASE | re.VERBOSE | re.UNICODE)

    def parse(self, transactions, value):
        match = self.re.match(value)
        if match:  # pragma: no branch
            self.logger.debug(
                'matched (%d) "%s" against "%s", got: %r',
                len(value), value, self.pattern, match.groupdict())
        else:  # pragma: no cover
            self.logger.info(
                'matching (%d) "%s" against "%s"', len(value), value,
                self.pattern)
            raise RuntimeError(
                'Unable to parse "%s" from "%s"' % (self, value),
                self, value)
        return match.groupdict()

    def __call__(self, transactions, value):
        return value

    def __new__(cls, *args, **kwargs):
        cls.name = cls.__name__

        words = re.findall('([A-Z][a-z0-9]+)', cls.__name__)
        cls.slug = '_'.join(w.lower() for w in words)
        cls.logger = logger.getChild(cls.name)

        return object.__new__(cls, *args, **kwargs)

    def __hash__(self):
        return self.id


class TransactionReferenceNumber(Tag):

    '''Transaction reference number

    Pattern: 16x
    '''
    id = 20
    pattern = r'(?P<transaction_reference>.{0,16})'


class RelatedReference(Tag):

    '''Related reference

    Pattern: 16x
    '''
    id = 21
    pattern = r'(?P<related_reference>.{0,16})'


class AccountIdentification(Tag):

    '''Account identification

    Pattern: 35x
    '''
    id = 25
    pattern = r'(?P<account_identification>.{0,35})'


class StatementNumber(Tag):

    '''Statement number / sequence number

    Pattern: 5n[/5n]
    '''
    id = 28
    pattern = r'''
    (?P<statement_number>\d{1,5})  # 5n
    (?:/(?P<sequence_number>\d{1,5}))?  # [/5n]
    $'''


class NonSwift(Tag):

    '''Non-swift extension for MT940 containing extra information. The
    actual definition is not consistent between banks so the current
    implementation is a tad limited. Feel free to extend the implmentation
    and create a pull request with a better version :)

    Pattern: 2!n35x
    '''
    id = 'NS'
    pattern = r'''
    (?P<non_swift>
        (\d{2}.{0,35})
        (\n\d{2}.{0,35})*
    )
    $'''
    sub_pattern = r'''
    (?P<ns_id>\d{2})(?P<ns_data>.{0,35})
    '''


class BalanceBase(Tag):

    '''Balance base

    Pattern: 1!a6!n3!a15d
    '''
    pattern = r'''^
    (?P<status>[DC])  # 1!a Debit/Credit
    (?P<year>\d{2})  # 6!n Value Date (YYMMDD)
    (?P<month>\d{2})
    (?P<day>\d{2})
    (?P<currency>.{3})  # 3!a Currency
    (?P<amount>[0-9,]{0,16})  # 15d Amount (includes decimal sign, so 16)
    '''

    def __call__(self, transactions, value):
        data = super(BalanceBase, self).__call__(transactions, value)
        data['amount'] = models.Amount(**data)
        data['date'] = models.Date(**data)
        return {
            self.slug: models.Balance(**data)
        }


class OpeningBalance(BalanceBase):
    id = 60


class FinalOpeningBalance(BalanceBase):
    id = '60F'


class IntermediateOpeningBalance(BalanceBase):
    id = '60M'


class Statement(Tag):

    '''Statement

    Pattern: 6!n[4!n]2a[1!a]15d1!a3!c16x[//16x]
    '''
    id = 61
    scope = models.Transaction
    pattern = r'''^
    (?P<year>\d{2})  # 6!n Value Date (YYMMDD)
    (?P<month>\d{2})
    (?P<day>\d{2})
    (?P<entry_month>\d{2})?  # [4!n] Entry Date (MMDD)
    (?P<entry_day>\d{2})?
    (?P<status>[A-Z]?[DC])  # 2a Debit/Credit Mark
    (?P<funds_code>[A-Z])? # [1!a] Funds Code (3rd character of the currency
                            # code, if needed)
    (?P<amount>[\d,]{1,15})  # 15d Amount
    (?P<id>[A-Z][A-Z0-9]{3})?  # 1!a3!c Transaction Type Identification Code
    (?P<customer_reference>.{0,16})  # 16x Customer Reference
    (//(?P<bank_reference>.{0,16}))?  # [//16x] Bank Reference
    (\n?(?P<extra_details>.{0,34}))?  # [34x] Supplementary Details
                                             # (this will be on a new/separate
                                             # line)
    $'''

    def __call__(self, transactions, value):
        data = super(Statement, self).__call__(transactions, value)
        data.setdefault('currency', transactions.currency)

        data['amount'] = models.Amount(**data)
        data['date'] = models.Date(**data)

        if data.get('entry_day') and data.get('entry_month'):
            data['entry_date'] = models.Date(
                day=data.get('entry_day'),
                month=data.get('entry_month'),
                year=str(data['date'].year),
            )
        return data


class ClosingBalance(BalanceBase):
    id = 62


class FinalClosingBalance(ClosingBalance):
    id = '62F'


class IntermediateClosingBalance(ClosingBalance):
    id = '62M'


class AvailableBalance(BalanceBase):
    id = 64


class ForwardAvailableBalance(BalanceBase):
    id = 65


class TransactionDetails(Tag):

    '''Transaction details

    Pattern: 6x65x
    '''
    id = 86
    scope = models.Transaction
    pattern = r'(?P<transaction_details>[\s\S]{0,330})'


class FileHeader1(Tag):

    '''File header
    '''
    id = 1
    # pattern = r'(?P<file_header1>.*)'
    pattern = r'F(?P<app_id>01|21)(?P<your_bic>[A-Z]{8,12})(?P<session_nb>\d{4})(?P<seq_nb>\d{6})'


class FileHeader2(Tag):

    '''File header
    '''
    id = 2
    # pattern = r'(?P<file_header2>.*)'
    pattern = r'(?P<mode>I|O)(?P<msg_type>\d{3})(?P<input_time>\d{4})(?P<mir_date>\d{6})(?P<mir_bic>[A-Z0-9]{8,12})(?P<mir_end>\d{10})(?P<output_date>\d{6})(?P<output_time>\d{4})(?P<priority>S|N|U)'

class FileHeader3(Tag):

    '''File header
    '''
    id = 3
    pattern = r'(?P<file_header3>.*)'


class FileHeader4(Tag):

    '''File header
    '''
    id = 4
    pattern = r'(?P<file_header4>.*)'

class FileFooter5(Tag):

    '''File header
    '''
    id = 5
    pattern = r'(?P<file_footer5>.*)'


@enum.unique
class Tags(enum.Enum):
    FILE_HEADER1 = FileHeader1()
    FILE_HEADER2 = FileHeader2()
    FILE_HEADER3 = FileHeader3()
    FILE_HEADER4 = FileHeader4()
    FILE_FOOTER5 = FileFooter5()
    TRANSACTION_REFERENCE_NUMBER = TransactionReferenceNumber()
    RELATED_REFERENCE = RelatedReference()
    ACCOUNT_IDENTIFICATION = AccountIdentification()
    STATEMENT_NUMBER = StatementNumber()
    OPENING_BALANCE = OpeningBalance()
    INTERMEDIATE_OPENING_BALANCE = IntermediateOpeningBalance()
    FINAL_OPENING_BALANCE = FinalOpeningBalance()
    STATEMENT = Statement()
    CLOSING_BALANCE = ClosingBalance()
    INTERMEDIATE_CLOSING_BALANCE = IntermediateClosingBalance()
    FINAL_CLOSING_BALANCE = FinalClosingBalance()
    AVAILABLE_BALANCE = AvailableBalance()
    FORWARD_AVAILABLE_BALANCE = ForwardAvailableBalance()
    TRANSACTION_DETAILS = TransactionDetails()
    NON_SWIFT = NonSwift()


TAG_BY_ID = {t.value.id: t.value for t in Tags}



