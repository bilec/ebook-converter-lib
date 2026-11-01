"""Metadata-only subset of Calibre's ebooks/metadata/mobi.py.

Adapted record/EXTH rebuilding for partial updates and joint MOBI/KF8 files.
"""

from struct import pack, unpack_from

from ebook_converter.ebooks.mobi import MobiError

__license__ = 'GPL v3'
__copyright__ = '2009, Kovid Goyal <kovid at kovidgoyal.net>'


class MetadataUpdater:

    def __init__(self, stream):
        self.stream = stream
        stream.seek(0)
        data = stream.read()
        if len(data) < 78 or data[60:68] != b'BOOKMOBI':
            raise MobiError('Not a BOOKMOBI file')
        count, = unpack_from('>H', data, 76)
        table_end = 78 + count * 8
        if count < 2 or table_end > len(data):
            raise MobiError('Invalid Palm database record table')
        offsets = [unpack_from('>I', data, 78 + index * 8)[0] for index in range(count)]
        if offsets[0] < table_end or offsets[-1] >= len(data) or any(
                left >= right for left, right in zip(offsets, offsets[1:])):
            raise MobiError('Invalid Palm database record offsets')
        self.header = bytearray(data[:offsets[0]])
        self.records = [data[start:stop] for start, stop in zip(offsets, offsets[1:] + [len(data)])]
        self.header_sections = [0]
        title, codec, records, length = self.fetchEXTHFields(0)
        version, = unpack_from('>I', self.records[0], 36)
        boundaries = [content for code, content in records if code == 121]
        if version != 8 and boundaries:
            if len(boundaries) != 1 or len(boundaries[0]) != 4:
                raise MobiError('Invalid KF8 header reference')
            section, = unpack_from('>I', boundaries[0])
            if section != 0xffffffff:
                if section < 2 or section >= count or self.records[section - 1] != b'BOUNDARY':
                    raise MobiError('Invalid KF8 boundary')
                self.fetchEXTHFields(section)
                if unpack_from('>I', self.records[section], 36)[0] != 8:
                    raise MobiError('Invalid KF8 header')
                self.header_sections.append(section)

    def fetchEXTHFields(self, section):
        record = self.records[section]
        if len(record) < 132 or record[16:20] != b'MOBI':
            raise MobiError('Invalid MOBI header')
        if unpack_from('>H', record, 12)[0] != 0:
            raise MobiError('DRM-protected books are unsupported')
        length, = unpack_from('>I', record, 20)
        end = 16 + length
        if length < 116 or end > len(record):
            raise MobiError('Invalid MOBI header length')
        codepage, = unpack_from('>I', record, 28)
        if codepage not in (65001, 1252):
            raise MobiError('Unsupported MOBI text encoding')
        codec = 'utf-8' if codepage == 65001 else 'cp1252'
        title_offset, title_length = unpack_from('>II', record, 84)
        if title_offset < end or title_offset + title_length > len(record):
            raise MobiError('Invalid MOBI title offsets')
        title = record[title_offset:title_offset + title_length]
        records = []
        if unpack_from('>I', record, 128)[0] & 0x40:
            if record[end:end + 4] != b'EXTH' or end + 12 > len(record):
                raise MobiError('Invalid EXTH header')
            exth_length, count = unpack_from('>II', record, end + 4)
            if exth_length < 12 or end + exth_length > title_offset:
                raise MobiError('Invalid EXTH length')
            position = end + 12
            for index in range(count):
                if position + 8 > end + exth_length:
                    raise MobiError('Truncated EXTH record')
                code, size = unpack_from('>II', record, position)
                if size < 8 or position + size > end + exth_length:
                    raise MobiError('Invalid EXTH record length')
                records.append((code, record[position + 8:position + size]))
                position += size
        return title, codec, records, length

    def create_exth(self, section, fields):
        title, codec, records, length = self.fetchEXTHFields(section)
        codes = {'authors': 100, 'publisher': 101, 'comments': 103, 'title': 503}
        replaced = {codes[field] for field in fields}
        records = [(code, content) for code, content in records if code not in replaced]
        for field, value in fields.items():
            values = value if field == 'authors' else [value]
            records.extend((codes[field], text.encode(codec)) for text in values if text)
        if 'title' in fields:
            title = fields['title'].encode(codec)
        body = b''.join(pack('>II', code, len(content) + 8) + content for code, content in records)
        exth = b'EXTH' + pack('>II', len(body) + 12, len(records)) + body
        exth += b'\0' * (4 - len(exth) % 4)
        original = self.records[section]
        title_offset, title_length = unpack_from('>II', original, 84)
        header = bytearray(original[:16 + length])
        if length == 0xe4:
            length = 0xe8
            header[20:24] = pack('>I', length)
            header.extend(pack('>I', 0xffffffff))
        header[128:132] = pack('>I', unpack_from('>I', header, 128)[0] | 0x40)
        header[84:92] = pack('>II', len(header) + len(exth), len(title))
        new_record = bytes(header) + exth + title + original[title_offset + title_length:]
        self.patchSection(section, new_record)

    def patchSection(self, section, new_record):
        self.records[section] = new_record

    def update(self, fields):
        if not fields:
            return
        for section in self.header_sections:
            self.create_exth(section, fields)
        offset = len(self.header)
        for index, record in enumerate(self.records):
            self.header[78 + index * 8:82 + index * 8] = pack('>I', offset)
            offset += len(record)
        self.stream.seek(0)
        self.stream.write(self.header)
        for record in self.records:
            self.stream.write(record)
        self.stream.truncate()


def get_metadata(stream):
    updater = MetadataUpdater(stream)
    title, codec, records, length = updater.fetchEXTHFields(0)
    fields = {'title': title.decode(codec), 'authors': [], 'publisher': '', 'comments': ''}
    codes = {101: 'publisher', 103: 'comments', 503: 'title'}
    for code, content in records:
        if code == 100:
            fields['authors'].append(content.decode(codec))
        elif code in codes:
            fields[codes[code]] = content.decode(codec)
    return fields


def set_metadata(stream, fields):
    MetadataUpdater(stream).update(fields)