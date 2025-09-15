from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Member(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    village = db.Column(db.String(50), nullable=True)
    membership_fee = db.Column(db.Float, default=5000.0)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.String(200), nullable=True)  # للملاحظات مثل "المعموق"
    is_new_member = db.Column(db.Boolean, default=True)  # تمييز العضو الجديد من السابق
    
    # علاقة مع المدفوعات
    payments = db.relationship('Payment', backref='member', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Member {self.name}>'
    
    def get_member_status(self):
        """تحديد حالة العضو (جديد أم سابق)"""
        if self.is_new_member:
            return "جديد"
        else:
            return "سابق"
    
    def get_member_status_class(self):
        """إرجاع CSS class لتمييز العضو بصرياً"""
        if self.is_new_member:
            return "new-member"
        else:
            return "old-member"
    
    def is_member_new_by_date(self, months_threshold=6):
        """تحديد ما إذا كان العضو جديد بناءً على تاريخ الانضمام"""
        if not self.join_date:
            return False
        
        months_since_join = (datetime.utcnow() - self.join_date).days / 30.44  # متوسط أيام الشهر
        return months_since_join <= months_threshold
    
    def get_total_paid(self):
        """حساب إجمالي المدفوعات"""
        total = sum(payment.amount for payment in self.payments if payment.is_paid)
        return total or 0
    
    def get_months_paid(self):
        """حساب عدد الأشهر المدفوعة"""
        count = sum(1 for payment in self.payments if payment.is_paid)
        return count or 0
    
    def get_payment_for_month(self, month, year):
        """الحصول على دفعة شهر معين"""
        for payment in self.payments:
            if payment.month == month and payment.year == year:
                return payment
        return None
    
    def get_current_month_payment(self):
        """التحقق من دفع الشهر الحالي"""
        current_month = datetime.now().month
        current_year = datetime.now().year
        payment = self.get_payment_for_month(current_month, current_year)
        return payment.is_paid if payment else False
    
    def get_remaining_balance(self):
        """حساب الرصيد المتبقي"""
        expected_annual = self.membership_fee * 12
        total_paid = self.get_total_paid()
        return max(0, expected_annual - total_paid)
    
    def get_unpaid_months(self):
        """الحصول على الأشهر غير المدفوعة"""
        unpaid = []
        for payment in self.payments:
            if not payment.is_paid:
                unpaid.append(f"{payment.month}/{payment.year}")
        return unpaid
    
    def get_monthly_payments_dict(self):
        """إرجاع المدفوعات الشهرية كـ dictionary للعرض في جدول Excel-like"""
        payments_dict = {}
        for payment in self.payments:
            month_key = f"month_{payment.month}_{payment.year}"
            payments_dict[month_key] = {
                'amount': payment.amount if payment.is_paid else 0,
                'is_paid': payment.is_paid,
                'payment_date': payment.payment_date
            }
        return payments_dict

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('member.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, default=1000.0)
    is_paid = db.Column(db.Boolean, default=False)
    payment_date = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f'<Payment {self.month}/{self.year} - {self.is_paid}>'

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cost = db.Column(db.Float, nullable=False)
    image_path = db.Column(db.String(200), nullable=True)
    created_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Project {self.title}>'

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.Column(db.String(50), nullable=True)
    
    def __repr__(self):
        return f'<Expense {self.description}: {self.amount}>'

class Assistance(db.Model):
    """نموذج المساعدات والمساهمات والإعانات"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)  # عنوان المساعدة
    description = db.Column(db.Text, nullable=True)  # وصف المساعدة
    source = db.Column(db.String(100), nullable=False)  # مصدر المساعدة (مؤسسة حكومية، منظمة، إلخ)
    assistance_type = db.Column(db.String(50), nullable=False)  # نوع المساعدة (أصول ثابتة، مبالغ مالية، مشاريع)
    amount = db.Column(db.Float, nullable=False)  # قيمة المساعدة
    date_received = db.Column(db.DateTime, default=datetime.utcnow)  # تاريخ الاستلام
    status = db.Column(db.String(50), default='مستلمة')  # حالة المساعدة
    notes = db.Column(db.Text, nullable=True)  # ملاحظات إضافية
    
    def __repr__(self):
        return f'<Assistance {self.title}: {self.amount}>'

class Spoilage(db.Model):
    """نموذج التوالف والأصول التالفة"""
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(200), nullable=False)  # اسم الصنف التالف
    description = db.Column(db.Text, nullable=True)  # وصف التلف
    original_value = db.Column(db.Float, nullable=False)  # القيمة الأصلية
    spoilage_value = db.Column(db.Float, nullable=False)  # قيمة التلف المخصومة
    spoilage_date = db.Column(db.DateTime, default=datetime.utcnow)  # تاريخ التلف
    spoilage_reason = db.Column(db.String(200), nullable=True)  # سبب التلف
    category = db.Column(db.String(50), nullable=True)  # فئة الصنف (كراسي، ألواح شمسية، بطاريات، إلخ)
    status = db.Column(db.String(50), default='تالف')  # حالة الصنف
    notes = db.Column(db.Text, nullable=True)  # ملاحظات إضافية
    
    def __repr__(self):
        return f'<Spoilage {self.item_name}: {self.spoilage_value}>'

class Asset(db.Model):
    """نموذج الأصول الثابتة"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # اسم الأصل
    description = db.Column(db.Text, nullable=True)  # وصف الأصل
    category = db.Column(db.String(50), nullable=True)  # فئة الأصل
    purchase_value = db.Column(db.Float, nullable=False)  # قيمة الشراء
    current_value = db.Column(db.Float, nullable=False)  # القيمة الحالية
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)  # تاريخ الشراء
    depreciation_rate = db.Column(db.Float, default=0.0)  # معدل الاستهلاك السنوي
    status = db.Column(db.String(50), default='فعال')  # حالة الأصل
    location = db.Column(db.String(100), nullable=True)  # موقع الأصل
    notes = db.Column(db.Text, nullable=True)  # ملاحظات
    
    def __repr__(self):
        return f'<Asset {self.name}: {self.current_value}>'
    
    def calculate_depreciation(self):
        """حساب الاستهلاك السنوي"""
        if self.depreciation_rate > 0:
            years_since_purchase = (datetime.utcnow() - self.purchase_date).days / 365.25
            depreciation_amount = self.purchase_value * (self.depreciation_rate / 100) * years_since_purchase
            return min(depreciation_amount, self.purchase_value)
        return 0
    
    def get_current_value(self):
        """حساب القيمة الحالية بعد الاستهلاك"""
        depreciation = self.calculate_depreciation()
        return max(0, self.purchase_value - depreciation)

