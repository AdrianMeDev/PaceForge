import gzip
import zlib
from datetime import UTC, datetime

import pytest

from accounts.models import User
from activities.models import Activity, ActivityFile
from activities.parsing import ActivityFileError, UnsupportedFileError, unpack
from activities.parsing.compressed import UnpackedTooLargeError, is_compressed
from activities.services import DuplicateActivityError, FileTooLargeError, import_activity

from .fit_builder import activity_file
from .tcx_builder import tcx_document

pytestmark = pytest.mark.django_db

START = datetime(2026, 11, 12, 6, 30, tzinfo=UTC)


@pytest.fixture
def alice() -> User:
    return User.objects.create_user("alice@example.com")


class TestUnpacking:
    def test_a_file_that_is_not_compressed_is_returned_as_it_is(self) -> None:
        data = activity_file()

        assert unpack(data, 10_000_000) is data
        assert is_compressed(data) is False

    def test_a_gzip_file_is_unpacked(self) -> None:
        data = activity_file()

        assert unpack(gzip.compress(data), 10_000_000) == data
        assert is_compressed(gzip.compress(data)) is True

    def test_what_follows_the_member_is_ignored(self) -> None:
        data = activity_file()

        assert unpack(gzip.compress(data) + b"trailing", 10_000_000) == data

    def test_the_result_may_be_exactly_the_limit(self) -> None:
        data = b"x" * 1000

        assert unpack(gzip.compress(data), 1000) == data

    def test_a_result_above_the_limit_is_refused_and_never_held(self) -> None:
        bomb = gzip.compress(b"\x00" * 50_000_000)  # about 50 kB that unpack to 50 MB

        with pytest.raises(UnpackedTooLargeError, match="too large"):
            unpack(bomb, 1000)

    @pytest.mark.parametrize(
        "data",
        [
            b"\x1f\x8b",
            b"\x1f\x8bnot a gzip stream at all",
            gzip.compress(b"hello")[:12],
            gzip.compress(b"hello")[:-3],
            b"\x1f\x8b\x08\x00" + b"\xff" * 40,
        ],
    )
    def test_broken_gzip_is_not_a_file_of_a_known_kind(self, data: bytes) -> None:
        with pytest.raises(UnsupportedFileError, match="neither a FIT nor a TCX"):
            unpack(data, 1000)

    def test_a_message_holds_nothing_of_the_data(self) -> None:
        with pytest.raises(ActivityFileError) as raised:
            unpack(b"\x1f\x8bSECRET-CONTENT", 1000)

        assert "SECRET" not in str(raised.value)

    def test_a_zlib_stream_without_the_gzip_header_is_not_unpacked(self) -> None:
        data = zlib.compress(activity_file())

        assert unpack(data, 10_000_000) == data


class TestImportingACompressedFile:
    def test_a_compressed_fit_file_is_imported_like_the_plain_one(self, alice: User) -> None:
        data = activity_file(start=START)

        activity = import_activity(alice, gzip.compress(data))

        assert (activity.sport, activity.source) == ("running", "fit_file")
        assert activity.start_time == START

    def test_a_compressed_tcx_file_is_imported_like_the_plain_one(self, alice: User) -> None:
        activity = import_activity(alice, gzip.compress(tcx_document(activity_id=START)))

        assert (activity.sport, activity.source) == ("running", "tcx_file")

    def test_the_original_that_is_stored_is_the_unpacked_file(self, alice: User) -> None:
        data = activity_file(start=START)

        activity = import_activity(alice, gzip.compress(data))

        stored = ActivityFile.objects.get(activity=activity)
        assert stored.read() == data
        assert stored.original_size == len(data)

    def test_the_same_activity_plain_and_compressed_is_one(self, alice: User) -> None:
        data = activity_file(start=START)
        first = import_activity(alice, data)

        with pytest.raises(DuplicateActivityError) as raised:
            import_activity(alice, gzip.compress(data))

        assert raised.value.existing_id == first.pk
        assert Activity.objects.count() == 1

    def test_the_hash_is_the_one_of_the_unpacked_file(self, alice: User) -> None:
        import hashlib

        data = activity_file(start=START)

        activity = import_activity(alice, gzip.compress(data))

        assert activity.source_hash == hashlib.sha256(data).hexdigest()

    def test_a_bomb_is_too_large_and_nothing_is_stored(self, alice: User, settings: object) -> None:
        settings.ACTIVITY_UPLOAD_MAX_BYTES = 10_000  # type: ignore[attr-defined]
        bomb = gzip.compress(b"\x00" * 5_000_000)
        assert len(bomb) < 10_000

        with pytest.raises(FileTooLargeError):
            import_activity(alice, bomb)

        assert (Activity.objects.count(), ActivityFile.objects.count()) == (0, 0)

    def test_broken_gzip_is_refused_and_nothing_is_stored(self, alice: User) -> None:
        with pytest.raises(UnsupportedFileError):
            import_activity(alice, b"\x1f\x8bbroken")

        assert Activity.objects.count() == 0

    def test_a_compressed_file_that_holds_no_activity_is_refused(self, alice: User) -> None:
        with pytest.raises(ActivityFileError):
            import_activity(alice, gzip.compress(b"plain text, no activity"))

        assert Activity.objects.count() == 0

    def test_the_compressed_file_itself_is_limited_too(self, alice: User, settings: object) -> None:
        data = activity_file(start=START)
        packed = gzip.compress(data)
        settings.ACTIVITY_UPLOAD_MAX_BYTES = len(packed) - 1  # type: ignore[attr-defined]

        with pytest.raises(FileTooLargeError):
            import_activity(alice, packed)
