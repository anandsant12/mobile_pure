"""
Creates and owns the underlying Appium driver session for the Android app
under test. The app is launched automatically as part of session creation
(app_package/app_activity are passed in the capabilities below) - the
agent/planner never need to "open" the app themselves; see planner.py.
"""

from config import settings


class DriverManager:
    def __init__(self):
        self.driver = None

    def start(self):
        # Imported lazily so nothing else needs Appium-Python-Client just to
        # import this module (e.g. quick unit tests of unrelated pieces).
        from appium import webdriver as appium_webdriver
        from appium.options.android import UiAutomator2Options

        options = UiAutomator2Options()
        options.device_name = settings.android_device_name
        options.automation_name = "UiAutomator2"
        options.platform_name = "Android"
        options.auto_grant_permissions = settings.android_auto_grant_permissions
        options.no_reset = settings.android_no_reset
        options.new_command_timeout = settings.android_new_command_timeout
        if settings.android_udid:
            options.udid = settings.android_udid
        if settings.android_platform_version:
            options.platform_version = settings.android_platform_version
        if settings.android_app_package:
            options.app_package = settings.android_app_package
        if settings.android_app_activity:
            options.app_activity = settings.android_app_activity

        self.driver = appium_webdriver.Remote(settings.appium_server_url, options=options)
        return self.driver

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
