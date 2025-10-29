# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_utc_timezone():
    """Set timezone to UTC for all unit tests.

    This ensures timestamp parsing and epoch calculations work correctly
    regardless of the system's local timezone. Matches the behavior of
    noxfile.py which sets TZ=UTC for unit test sessions.
    """
    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"

    # time.tzset() reloads the timezone from TZ environment variable
    import time

    time.tzset()

    yield

    # Restore original timezone after tests
    if original_tz is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original_tz
    time.tzset()
