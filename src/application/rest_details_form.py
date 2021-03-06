#ruri

from wtforms import Form, StringField, RadioField, SelectField, TextAreaField, validators
from wtforms.fields import IntegerField, StringField, TimeField, DecimalField
# from wtforms_components import TimeField

class RestaurantDetailsForm(Form):
    rest_name = StringField('Restaurant Name', [validators.Length(min=1, max=150), validators.DataRequired()])
    rest_contact = IntegerField('Contact Number',  [validators.Optional(), validators.DataRequired()])
    rest_hour_open = TimeField('Opening Hours:', [validators.Optional(), validators.DataRequired()])
    rest_hour_close = TimeField(' ', [validators.Optional(), validators.DataRequired()])
    rest_address1 = StringField('Address line 1', [validators.Optional(), validators.DataRequired()])
    rest_address2 = StringField('Address line 2', [validators.Optional(), validators.DataRequired()])
    rest_postcode = StringField('Postal Code', [validators.Optional(), validators.DataRequired()])
    rest_desc = TextAreaField('Restaurant Description:', [validators.Optional(), validators.DataRequired()])
    rest_bank = StringField('Bank Account', [validators.Optional(), validators.DataRequired()])
    rest_del1 = DecimalField('1-2km:', [validators.Optional(), validators.DataRequired()])
    rest_del2 = DecimalField('2-4km:', [validators.Optional(), validators.DataRequired()])
    rest_del3 = DecimalField('4-6km:', [validators.Optional(), validators.DataRequired()])
    rest_del4 = DecimalField('6-8km:', [validators.Optional(), validators.DataRequired()])
    rest_del5 = DecimalField('>9km:', [validators.Optional(), validators.DataRequired()])
