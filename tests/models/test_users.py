from sqlalchemy.sql import select

from redash import redis_connection
from redash.models import ApiUser, User, db
from redash.models.users import LAST_ACTIVE_KEY, sync_last_active_at
from redash.utils import dt_from_timestamp
from tests import BaseTestCase, authenticated_user


class TestUserUpdateGroupAssignments(BaseTestCase):
    def test_default_group_always_added(self):
        user = self.factory.create_user()

        user.update_group_assignments(["g_unknown"])
        db.session.refresh(user)

        self.assertCountEqual([user.org.default_group.id], user.group_ids)

    def test_update_group_assignments(self):
        user = self.factory.user
        new_group = self.factory.create_group(name="g1")

        user.update_group_assignments(["g1"])
        db.session.refresh(user)

        self.assertCountEqual([user.org.default_group.id, new_group.id], user.group_ids)


class TestUserFindByEmail(BaseTestCase):
    def test_finds_users(self):
        user = self.factory.create_user(email="test@example.com")
        user2 = self.factory.create_user(email="test@example.com", org=self.factory.create_org())

        users = User.find_by_email(user.email)
        self.assertIn(user, users)
        self.assertIn(user2, users)

    def test_finds_users_case_insensitive(self):
        user = self.factory.create_user(email="test@example.com")

        users = User.find_by_email("test@EXAMPLE.com")
        self.assertIn(user, users)


class TestUserGetByEmailAndOrg(BaseTestCase):
    def test_get_user_by_email_and_org(self):
        user = self.factory.create_user(email="test@example.com")

        found_user = User.get_by_email_and_org(user.email, user.org)
        self.assertEqual(user, found_user)

    def test_get_user_by_email_and_org_case_insensitive(self):
        user = self.factory.create_user(email="test@example.com")

        found_user = User.get_by_email_and_org("TEST@example.com", user.org)
        self.assertEqual(user, found_user)


class TestUserSearch(BaseTestCase):
    def test_non_unicode_search_string(self):
        user = self.factory.create_user(name="אריק")

        assert user in db.session.scalars(User.search(User.all(user.org), term="א")).all()


class TestUserRegenerateApiKey(BaseTestCase):
    def test_regenerate_api_key(self):
        user = self.factory.user
        before_api_key = user.api_key
        user.regenerate_api_key()

        # check committed by research
        user = db.session.get(User, user.id)
        self.assertNotEqual(user.api_key, before_api_key)


class TestUserDetail(BaseTestCase):
    # def setUp(self):
    #     super(TestUserDetail, self).setUp()
    #     # redis_connection.flushdb()

    def test_userdetail_db_default(self):
        with authenticated_user(self.client) as user:
            self.assertEqual(user.details, {})
            self.assertIsNone(user.active_at)

    def test_userdetail_db_default_save(self):
        with authenticated_user(self.client) as user:
            user.details["test"] = 1
            db.session.commit()

            user_reloaded = db.session.scalar(select(User).filter_by(id=user.id))
            self.assertEqual(user.details["test"], 1)
            self.assertEqual(
                user_reloaded, db.session.scalar(select(User).where(User.details["test"].astext.cast(db.Integer) == 1))
            )

    def test_sync(self):
        with authenticated_user(self.client) as user:
            self.client.get("/default/")
            timestamp = dt_from_timestamp(redis_connection.hget(LAST_ACTIVE_KEY, user.id))
            sync_last_active_at()

            user_reloaded = db.session.scalar(select(User).where(User.id == user.id))
            self.assertIn("active_at", user_reloaded.details)
            self.assertEqual(user_reloaded.active_at, timestamp)


class TestUserGetActualUser(BaseTestCase):
    def test_default_user(self):
        user_email = "test@example.com"
        user = self.factory.create_user(email=user_email)
        self.assertEqual(user.get_actual_user(), user_email)

    def test_api_user(self):
        user_email = "test@example.com"
        user = self.factory.create_user(email=user_email)
        api_user = ApiUser(user.api_key, user.org, user.group_ids)
        self.assertEqual(api_user.get_actual_user(), repr(api_user))
