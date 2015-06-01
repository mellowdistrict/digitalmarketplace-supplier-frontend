import re

from flask import Flask, request, redirect
from flask_login import LoginManager
from flask_featureflags import FeatureFlag
from flask_featureflags.contrib.inline import InlineFeatureFlag
from flask._compat import string_types
from dmutils import apiclient, logging, config, proxy_fix

from config import configs
from .model import User

data_api_client = apiclient.DataAPIClient()
login_manager = LoginManager()
feature_flags = FeatureFlag()


def create_app(config_name):
    application = Flask(__name__,
                        static_folder='static/',
                        static_url_path=configs[config_name].STATIC_URL_PATH)
    application.config.from_object(configs[config_name])
    configs[config_name].init_app(application)
    config.init_app(application)

    from .main import main as main_blueprint
    from .status import status as status_blueprint

    proxy_fix.init_app(application)
    login_manager.init_app(application)
    feature_flags.init_app(application)
    feature_flags.add_handler(InlineFeatureFlag())
    logging.init_app(application)
    data_api_client.init_app(application)

    application.register_blueprint(status_blueprint,
                                   url_prefix='/suppliers')
    application.register_blueprint(main_blueprint,
                                   url_prefix='/suppliers')
    login_manager.login_view = 'main.render_login'
    main_blueprint.config = application.config.copy()

    @application.before_request
    def remove_trailing_slash():
        if request.path.endswith('/'):
            return redirect(request.path[:-1], code=301)

    return application


@login_manager.user_loader
def load_user(user_id):
    return User.from_json(data_api_client.get_user(user_id=int(user_id)))


def config_attrs(config):
    """Returns config attributes from a Config object"""
    p = re.compile('^[A-Z_]+$')
    return filter(lambda attr: bool(p.match(attr)), dir(config))


def convert_to_boolean(value):
    """Turn strings to bools if they look like them

    Truthy things should be True
    >>> for truthy in ['true', 'on', 'yes', '1']:
    ...   assert convert_to_boolean(truthy) == True

    Falsey things should be False
    >>> for falsey in ['false', 'off', 'no', '0']:
    ...   assert convert_to_boolean(falsey) == False

    Other things should be unchanged
    >>> for value in ['falsey', 'other', True, 0]:
    ...   assert convert_to_boolean(value) == value
    """
    if isinstance(value, string_types):
        if value.lower() in ['t', 'true', 'on', 'yes', '1']:
            return True
        elif value.lower() in ['f', 'false', 'off', 'no', '0']:
            return False

    return value
