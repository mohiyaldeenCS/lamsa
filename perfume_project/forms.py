from flask_wtf import FlaskForm
from math import isfinite
from wtforms import FloatField, HiddenField, IntegerField, PasswordField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError


def trim(value):
    return value.strip() if isinstance(value, str) else value


def finite_price(form, field):
    if field.data is not None and not isfinite(field.data):
        raise ValidationError('أدخل سعرًا صحيحًا.')


class TrimmedStringField(StringField):
    def __init__(self, *args, **kwargs):
        kwargs['filters'] = [trim, *kwargs.get('filters', [])]
        super().__init__(*args, **kwargs)


class TrimmedTextAreaField(TextAreaField):
    def __init__(self, *args, **kwargs):
        kwargs['filters'] = [trim, *kwargs.get('filters', [])]
        super().__init__(*args, **kwargs)


class EmptyForm(FlaskForm):
    pass


class RegisterForm(FlaskForm):
    username = TrimmedStringField("اسم المستخدم", validators=[DataRequired(message="أدخل اسم المستخدم."), Length(3, 80, message="يجب أن يكون بين 3 و80 حرفًا.")])
    password = PasswordField("كلمة المرور", validators=[DataRequired(message="أدخل كلمة المرور."), Length(6, 128, message="استخدم 6 أحرف على الأقل.")])
    password2 = PasswordField("تأكيد كلمة المرور", validators=[DataRequired(message="أعد كتابة كلمة المرور."), EqualTo("password", message="كلمتا المرور غير متطابقتين.")])
    submit = SubmitField("إنشاء الحساب")


class LoginForm(FlaskForm):
    username = TrimmedStringField("اسم المستخدم", validators=[DataRequired(message="أدخل اسم المستخدم."), Length(max=80)])
    password = PasswordField("كلمة المرور", validators=[DataRequired(message="أدخل كلمة المرور."), Length(max=128)])
    submit = SubmitField("تسجيل الدخول")


class PerfumeForm(FlaskForm):
    name = TrimmedStringField("اسم العطر", validators=[DataRequired(message="اسم العطر مطلوب."), Length(max=120)])
    brand = TrimmedStringField("الدار العطرية", validators=[DataRequired(message="اسم الدار مطلوب."), Length(max=120)])
    description = TrimmedTextAreaField("الوصف والنوتات", validators=[DataRequired(message="أضف وصفًا موجزًا للعطر."), Length(max=5000)])
    price = FloatField("السعر (ر.س)", validators=[InputRequired(message="السعر مطلوب."), finite_price, NumberRange(min=0, max=1000000, message="أدخل سعرًا بين صفر ومليون.")])
    stock = IntegerField("المخزون", validators=[InputRequired(message="المخزون مطلوب."), NumberRange(min=0, max=1000000, message="أدخل مخزونًا بين صفر ومليون.")])
    submit = SubmitField("حفظ العطر")


class CheckoutForm(FlaskForm):
    full_name = TrimmedStringField("الاسم الكامل", validators=[DataRequired(), Length(min=2, max=120)])
    phone = TrimmedStringField("رقم الجوال", validators=[DataRequired(), Length(min=7, max=30), Regexp(r"^\+?[0-9٠-٩][0-9٠-٩ ()-]+$", message="أدخل رقم جوال صحيحًا.")])
    city = TrimmedStringField("المدينة", validators=[DataRequired(), Length(min=2, max=100)])
    address = TrimmedTextAreaField("العنوان", validators=[DataRequired(), Length(min=5, max=500)])
    note = TrimmedTextAreaField("ملاحظة (اختياري)", validators=[Optional(), Length(max=1000)])
    checkout_token = HiddenField(validators=[DataRequired(), Length(max=96)])
    submit = SubmitField("تأكيد الطلب التجريبي")

    def validate_phone(self, field):
        if not 7 <= sum(character.isdigit() for character in field.data) <= 15:
            raise ValidationError('أدخل رقم جوال من 7 إلى 15 رقمًا.')


class FragranceFinderForm(FlaskForm):
    family = SelectField("أي نوتات تفضّل؟", choices=[('any', 'أحب الاكتشاف'), ('floral', 'الورد والزهور'), ('fresh', 'الحمضيات والانتعاش'), ('woody', 'العود والمسك'), ('gourmand', 'الفانيلا والدفء')], validators=[DataRequired()])
    occasion = SelectField("متى ترتدي عطرك؟", choices=[('everyday', 'كل يوم'), ('evening', 'المناسبات والمساء'), ('gift', 'أبحث عن هدية')], validators=[DataRequired()])
    intensity = SelectField("ما الحضور الذي يناسبك؟", choices=[('soft', 'ناعم وقريب'), ('balanced', 'متوازن'), ('bold', 'غني ولافت')], validators=[DataRequired()])
    submit = SubmitField("اكتشف اختياراتي")


ORDER_STATUS_LABELS = {'pending': 'قيد المراجعة', 'confirmed': 'مؤكد', 'preparing': 'قيد التجهيز', 'completed': 'مكتمل', 'cancelled': 'ملغي'}


class OrderStatusForm(FlaskForm):
    status = SelectField("حالة الطلب", choices=list(ORDER_STATUS_LABELS.items()), validators=[DataRequired()])
    submit = SubmitField("تحديث الحالة")
