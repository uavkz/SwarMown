"""
Django settings for swarmown project.

Generated by 'django-admin startproject' using Django 3.0.3.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""

import os
from itertools import chain
from typing import Sequence

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'vjx7%%jei)hu8x#1lq7#q*$of!&-1@*^ywjm2qwv&3w2&!8a4t'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'rest_framework',
    'mainapp',
    'restapp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'swarmown.urls'

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_jwt.authentication.JSONWebTokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ),
}

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates'), ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'swarmown.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}


# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = (
    os.path.join(BASE_DIR, 'staticfiles'),
)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# MOnkey patch!
def new_edges(self) -> Sequence:
    """
    Returns edges of the polygon.

    Time complexity:
        ``O(vertices_count)``
    Memory complexity:
        ``O(vertices_count)``

    where

        .. code-block:: python

            vertices_count = (len(self.border.vertices)
                              + sum(len(hole.vertices)\
for hole in self.holes))

    >>> from gon.base import Contour, Point, Polygon, Segment
    >>> polygon = Polygon(Contour([Point(0, 0), Point(6, 0), Point(6, 6),
    ...                            Point(0, 6)]),
    ...                   [Contour([Point(2, 2), Point(2, 4), Point(4, 4),
    ...                             Point(4, 2)])])
    >>> polygon.edges == [Segment(Point(0, 6), Point(0, 0)),
    ...                   Segment(Point(0, 0), Point(6, 0)),
    ...                   Segment(Point(6, 0), Point(6, 6)),
    ...                   Segment(Point(6, 6), Point(0, 6)),
    ...                   Segment(Point(4, 2), Point(2, 2)),
    ...                   Segment(Point(2, 2), Point(2, 4)),
    ...                   Segment(Point(2, 4), Point(4, 4)),
    ...                   Segment(Point(4, 4), Point(4, 2))]
    True
    """

    from gon.base import Point as GonPoint, Contour as GonContour, Polygon as GonPolygon
    from ground.core.hints import Point as GroundPoint, Contour as GroundContour, Polygon as GroundPolygon

    def ground_point_to_gon_point(ground_point: GroundPoint) -> GonPoint:
        return GonPoint(ground_point.x, ground_point.y)

    def ground_contour_to_gon_contour(ground_contour: GroundContour) -> GonContour:
        vertices = [ground_point_to_gon_point(vertex) for vertex in ground_contour.vertices]
        return GonContour(vertices)

    if isinstance(self.border, GroundContour):
        self._border = ground_contour_to_gon_contour(self.border)

    flatten = chain.from_iterable
    return list(chain(self.border.segments,
                      flatten(hole.segments for hole in self.holes)))

from gon.core.polygon import Polygon
Polygon.edges = property(new_edges)
# MOnkey patch!