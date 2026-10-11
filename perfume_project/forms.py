from flask_wtf import FlaskForm
from wtforms import FloatField, IntegerField, PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, NumberRange


class EmptyForm(FlaskForm):
    pass


class RegisterForm(FlaskForm):
    username = StringField("اسم المستخدم", validators=[DataRequired(message="أدخل اسم المستخدم."), Length(3, 80, message="يجب أن يكون بين 3 و80 حرفًا.")])
    password = PasswordField("كلمة المرور", validators=[DataRequired(message="أدخل كلمة المرور."), Length(6, 128, message="استخدم 6 أحرف على الأقل.")])
    password2 = PasswordField("تأكيد كلمة المرور", validators=[DataRequired(message="أعد كتابة كلمة المرور."), EqualTo("password", message="كلمتا المرور غير متطابقتين.")])
    submit = SubmitField("إنشاء الحساب")


class LoginForm(FlaskForm):
    username = StringField("اسم المستخدم", validators=[DataRequired(message="أدخل اسم المستخدم.")])
    password = PasswordField("كلمة المرور", validators=[DataRequired(message="أدخل كلمة المرور.")])
    submit = SubmitField("تسجيل الدخول")


class PerfumeForm(FlaskForm):
    name = StringField("اسم العطر", validators=[DataRequired(message="اسم العطر مطلوب.")])
    brand = StringField("الدار العطرية", validators=[DataRequired(message="اسم الدار مطلوب.")])
    description = TextAreaField("الوصف والنوتات", validators=[DataRequired(message="أضف وصفًا موجزًا للعطر.")])
    price = FloatField("السعر (ر.س)", validators=[DataRequired(message="السعر مطلوب."), NumberRange(min=0, message="السعر لا يمكن أن يكون سالبًا.")])
    stock = IntegerField("المخزون", validators=[DataRequired(message="المخزون مطلوب."), NumberRange(min=0, message="المخزون لا يمكن أن يكون سالبًا.")])
    submit = SubmitField("حفظ العطر")
