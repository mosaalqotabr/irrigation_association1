from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import pandas as pd
import os
from datetime import datetime, date
import io
from docx import Document
from docx.shared import Inches
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile

from config import Config
# إصلاح 1: إضافة النماذج الناقصة
from models import db, Member, Payment, Project, Expense, Assistance, Spoilage, Asset

app = Flask(__name__)
app.config.from_object(Config)

# تهيئة قاعدة البيانات
db.init_app(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'xlsx', 'xls'}

def get_current_year_months():
    """الحصول على الأشهر الحالية للسنة المالية"""
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # تحديد السنة المالية (من نوفمبر إلى أكتوبر)
    if current_month >= 11:  # نوفمبر وديسمبر
        financial_year_start = current_year
        financial_year_end = current_year + 1
    else:  # يناير إلى أكتوبر
        financial_year_start = current_year - 1
        financial_year_end = current_year
    
    months = []
    # أشهر السنة المالية
    for month in [11, 12]:  # نوفمبر وديسمبر
        months.append((f'شهر{month}', month, financial_year_start))
    
    for month in range(1, 11):  # يناير إلى أكتوبر
        months.append((f'شهر{month}', month, financial_year_end))
    
    return months

def admin_required(f):
    """ديكوريتر للتحقق من تسجيل دخول المدير"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('يجب تسجيل الدخول أولاً', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    total_members = Member.query.count()
    total_projects = Project.query.count()
    total_paid = db.session.query(db.func.sum(Payment.amount)).filter(Payment.is_paid == True).scalar() or 0
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    balance = total_paid - total_expenses
    
    recent_projects = Project.query.order_by(Project.created_date.desc()).limit(3).all()
    
    return render_template('index.html', 
                         total_members=total_members,
                         total_projects=total_projects,
                         total_paid=total_paid,
                         total_expenses=total_expenses,
                         balance=balance,
                         recent_projects=recent_projects)

@app.route('/members')
def members():
    """صفحة المشتركين"""
    members_list = Member.query.all()
    
    # إعداد بيانات المدفوعات لكل عضو
    members_data = []
    for member in members_list:
        member_info = {
            'id': member.id,
            'number': member.member_number,
            'name': member.name,
            'village': member.village or 'غير محدد',
            'membership_fee': member.membership_fee,
            'total_paid': member.get_total_paid(),
            'unpaid_months': member.get_unpaid_months(),
            'payments': {}
        }
        
        # إضافة بيانات المدفوعات الشهرية
        for payment in member.payments:
            month_key = f"{payment.month}/{payment.year}"
            member_info['payments'][month_key] = payment.is_paid
            
        members_data.append(member_info)
    
    return render_template('members.html', members=members_data)

@app.route('/projects')
def projects():
    """صفحة المشاريع"""
    projects_list = Project.query.order_by(Project.created_date.desc()).all()
    return render_template('projects.html', projects=projects_list)

@app.route('/expenses')
def expenses():
    """صفحة المصروفات"""
    expenses_list = Expense.query.order_by(Expense.date.desc()).all()
    
    # حساب إجمالي المصروفات
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    
    # تجميع المصروفات حسب الفئة
    expenses_by_category = {}
    for expense in expenses_list:
        category = expense.category or 'أخرى'
        if category not in expenses_by_category:
            expenses_by_category[category] = 0
        expenses_by_category[category] += expense.amount
    
    return render_template('expenses.html', 
                         expenses=expenses_list,
                         total_expenses=total_expenses,
                         expenses_by_category=expenses_by_category)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """تسجيل دخول المدير"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == app.config['ADMIN_USERNAME'] and password == app.config['ADMIN_PASSWORD']:
            session['admin_logged_in'] = True
            flash('تم تسجيل الدخول بنجاح', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    """تسجيل خروج المدير"""
    session.pop('admin_logged_in', None)
    flash('تم تسجيل الخروج بنجاح', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """لوحة تحكم المدير"""
    stats = {
        'total_members': Member.query.count(),
        'total_projects': Project.query.count(),
        'total_paid': db.session.query(db.func.sum(Payment.amount)).filter(Payment.is_paid == True).scalar() or 0,
        'total_expenses': db.session.query(db.func.sum(Expense.amount)).scalar() or 0,
    }
    stats['balance'] = stats['total_paid'] - stats['total_expenses']
    
    # الأعضاء المتأخرين في الدفع
    unpaid_members = []
    for member in Member.query.all():
        unpaid_months = member.get_unpaid_months()
        if unpaid_months:
            unpaid_members.append({
                'name': member.name,
                'unpaid_months': unpaid_months
            })
    
    return render_template('admin/dashboard.html', stats=stats, unpaid_members=unpaid_members)

@app.route("/admin/members")
@admin_required
def admin_members():
    """إدارة المشتركين مع دعم السنوات"""
    current_year = request.args.get('year', type=int, default=datetime.now().year)
    members_list = Member.query.all()
    
    # إعداد بيانات المشتركين مع المدفوعات للسنة المحددة
    members_data = []
    for member in members_list:
        member_info = {
            'id': member.id,
            'member_number': member.member_number,
            'name': member.name,
            'village': member.village,
            'membership_fee': member.membership_fee,
            'get_payment_for_month': member.get_payment_for_month
        }
        members_data.append(member_info)
    
    return render_template('admin/members_manage.html', 
                         members=members_data, 
                         current_year=current_year)

@app.route("/admin/payments")
@admin_required
def admin_payments():
    """إدارة المدفوعات الشهرية"""
    current_month = request.args.get('month', type=int, default=datetime.now().month)
    current_year = request.args.get('year', type=int, default=datetime.now().year)

    members_list = Member.query.all()
    payment_data = []
    paid_count = 0
    unpaid_count = 0
    total_amount = 0

    for member in members_list:
        payment = Payment.query.filter_by(
            member_id=member.id,
            month=current_month,
            year=current_year
        ).first()

        is_paid = payment.is_paid if payment else False
        amount = payment.amount if payment else member.membership_fee / 12  # افتراض مبلغ شهري

        if is_paid:
            paid_count += 1
            total_amount += amount
        else:
            unpaid_count += 1

        payment_data.append({
            'member': member,
            'is_paid': is_paid,
            'amount': amount,
            'total_paid': member.get_total_paid(),
            'months_paid': member.get_months_paid(),
            'remaining_balance': member.get_remaining_balance()
        })

    return render_template('admin/payments_manage.html',
                           payment_data=payment_data,
                           current_month=current_month,
                           current_year=current_year,
                           paid_count=paid_count,
                           unpaid_count=unpaid_count,
                           total_members=len(members_list),
                           total_amount=total_amount)

@app.route("/admin/toggle_payment/<int:member_id>/<int:month>/<int:year>", methods=['POST'])
@admin_required
def admin_toggle_payment(member_id, month, year):
    """تبديل حالة دفع عضو لشهر معين"""
    try:
        payment = Payment.query.filter_by(member_id=member_id, month=month, year=year).first()
        if payment:
            payment.is_paid = not payment.is_paid
            payment.payment_date = datetime.now() if payment.is_paid else None
        else:
            # إذا لم تكن هناك دفعة موجودة، أنشئ واحدة واجعلها مدفوعة
            member = Member.query.get_or_404(member_id)
            payment = Payment(
                member_id=member_id,
                month=month,
                year=year,
                amount=member.membership_fee / 12,  # مبلغ افتراضي
                is_paid=True,
                payment_date=datetime.now()
            )
            db.session.add(payment)
        db.session.commit()
        flash('تم تحديث حالة الدفع بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في تحديث حالة الدفع: {str(e)}', 'error')
    return redirect(url_for('admin_payments', month=month, year=year))

@app.route("/admin/expenses")
@admin_required
def admin_expenses():
    """إدارة المصروفات"""
    expenses_list = Expense.query.order_by(Expense.date.desc()).all()
    
    # حساب إجمالي المصروفات
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    
    # تجميع المصروفات حسب الفئة
    expenses_by_category = {}
    for expense in expenses_list:
        category = expense.category or 'أخرى'
        if category not in expenses_by_category:
            expenses_by_category[category] = 0
        expenses_by_category[category] += expense.amount
    
    return render_template('admin/expenses_manage.html', 
                         expenses=expenses_list,
                         total_expenses=total_expenses,
                         expenses_by_category=expenses_by_category)

@app.route('/admin/projects')
@admin_required
def admin_projects():
    """إدارة المشاريع"""
    projects_list = Project.query.order_by(Project.created_date.desc()).all()
    return render_template('admin/projects_manage.html', projects=projects_list)

@app.route('/admin/add_member', methods=['POST'])
@admin_required
def add_member():
    """إضافة مشترك جديد"""
    try:
        member_number = int(request.form['member_number'])
        name = request.form['name']
        village = request.form.get('village', '')
        membership_fee = float(request.form.get('membership_fee', 5000))
        
        # التحقق من عدم وجود رقم العضو مسبقاً
        existing_member = Member.query.filter_by(member_number=member_number).first()
        if existing_member:
            flash('رقم العضو موجود مسبقاً', 'error')
            return redirect(url_for('admin_dashboard'))
        
        # إنشاء العضو الجديد
        member = Member(
            member_number=member_number,
            name=name,
            village=village,
            membership_fee=membership_fee
        )
        db.session.add(member)
        db.session.flush()
        
        # إنشاء المدفوعات الشهرية للسنة المالية الحالية
        months = get_current_year_months()
        for month_name, month_num, year in months:
            payment = Payment(
                member_id=member.id,
                month=month_num,
                year=year,
                amount=1000,
                is_paid=False
            )
            db.session.add(payment)
        
        db.session.commit()
        flash('تم إضافة المشترك بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في إضافة المشترك: {str(e)}', 'error')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_expense', methods=['POST'])
@admin_required
def add_expense():
    """إضافة مصروف جديد"""
    try:
        description = request.form['description']
        amount = float(request.form['amount'])
        category = request.form.get('category', 'أخرى')
        date_str = request.form.get('date')
        
        # تحويل التاريخ
        expense_date = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()
        
        expense = Expense(
            description=description,
            amount=amount,
            category=category,
            date=expense_date
        )
        db.session.add(expense)
        db.session.commit()
        
        flash('تم إضافة المصروف بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في إضافة المصروف: {str(e)}', 'error')
    
    return redirect(url_for('admin_expenses'))

@app.route('/admin/add_project', methods=['POST'])
@admin_required
def add_project():
    """إضافة مشروع جديد"""
    try:
        title = request.form['title']
        description = request.form.get('description', '')
        cost = float(request.form['cost'])
        
        project = Project(
            title=title,
            description=description,
            cost=cost
        )
        db.session.add(project)
        db.session.commit()
        
        flash('تم إضافة المشروع بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في إضافة المشروع: {str(e)}', 'error')
    
    return redirect(url_for('admin_projects'))

@app.route('/admin/update_payment', methods=['POST'])
@admin_required
def update_payment():
    """تحديث حالة الدفع"""
    try:
        payment_data = request.get_json()
        member_id = payment_data['member_id']
        month = payment_data['month']
        year = payment_data['year']
        is_paid = payment_data['is_paid']
        
        # البحث عن الدفعة أو إنشاؤها
        payment = Payment.query.filter_by(
            member_id=member_id,
            month=month,
            year=year
        ).first()
        
        if not payment:
            payment = Payment(
                member_id=member_id,
                month=month,
                year=year,
                amount=1000,
                is_paid=is_paid,
                payment_date=datetime.now() if is_paid else None
            )
            db.session.add(payment)
        else:
            payment.is_paid = is_paid
            payment.payment_date = datetime.now() if is_paid else None
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/delete_member/<int:member_id>', methods=['POST'])
@admin_required
def delete_member(member_id):
    """حذف مشترك"""
    try:
        member = Member.query.get_or_404(member_id)
        db.session.delete(member)
        db.session.commit()
        flash('تم حذف المشترك بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في حذف المشترك: {str(e)}', 'error')
    
    return redirect(url_for('admin_members'))

@app.route('/admin/delete_expense/<int:expense_id>', methods=['POST'])
@admin_required
def delete_expense(expense_id):
    """حذف مصروف"""
    try:
        expense = Expense.query.get_or_404(expense_id)
        db.session.delete(expense)
        db.session.commit()
        flash('تم حذف المصروف بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في حذف المصروف: {str(e)}', 'error')
    
    return redirect(url_for('admin_expenses'))

@app.route('/admin/delete_project/<int:project_id>', methods=['POST'])
@admin_required
def delete_project(project_id):
    """حذف مشروع"""
    try:
        project = Project.query.get_or_404(project_id)
        db.session.delete(project)
        db.session.commit()
        flash('تم حذف المشروع بنجاح', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في حذف المشروع: {str(e)}', 'error')
    
    return redirect(url_for('admin_projects'))

# مسارات إضافية لإدارة المصروفات
@app.route('/admin/edit_expense/<int:expense_id>', methods=['GET', 'POST'])
@admin_required
def edit_expense(expense_id):
    """تعديل مصروف"""
    expense = Expense.query.get_or_404(expense_id)
    
    if request.method == 'POST':
        try:
            expense.description = request.form['description']
            expense.amount = float(request.form['amount'])
            expense.category = request.form.get('category', 'أخرى')
            
            date_str = request.form.get('date')
            if date_str:
                expense.date = datetime.strptime(date_str, '%Y-%m-%d')
            
            db.session.commit()
            flash('تم تحديث المصروف بنجاح', 'success')
            return redirect(url_for('admin_expenses'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ في تحديث المصروف: {str(e)}', 'error')
    
    return render_template('admin/edit_expense.html', expense=expense)

@app.route('/admin/expense_categories')
@admin_required
def expense_categories():
    """إدارة فئات المصروفات"""
    # الحصول على جميع الفئات المستخدمة
    categories = db.session.query(Expense.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    # إضافة فئات افتراضية إذا لم تكن موجودة
    default_categories = ['صيانة', 'مواد', 'رواتب', 'وقود', 'كهرباء', 'أخرى']
    for cat in default_categories:
        if cat not in categories:
            categories.append(cat)
    
    return render_template('admin/expense_categories.html', categories=categories)

@app.route('/admin/expense_reports')
@admin_required
def expense_reports():
    """تقارير المصروفات"""
    # تقرير شهري
    monthly_expenses = db.session.query(
        db.func.strftime('%Y-%m', Expense.date).label('month'),
        db.func.sum(Expense.amount).label('total')
    ).group_by(db.func.strftime('%Y-%m', Expense.date)).all()
    
    # تقرير حسب الفئة
    category_expenses = db.session.query(
        Expense.category,
        db.func.sum(Expense.amount).label('total')
    ).group_by(Expense.category).all()
    
    # إجمالي المصروفات
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    
    return render_template('admin/expense_reports.html', 
                         monthly_expenses=monthly_expenses,
                         category_expenses=category_expenses,
                         total_expenses=total_expenses)

@app.route('/admin/bulk_add_expenses', methods=['GET', 'POST'])
@admin_required
def bulk_add_expenses():
    """إضافة مصروفات متعددة"""
    if request.method == 'POST':
        try:
            expenses_data = request.get_json()
            
            for expense_data in expenses_data:
                expense = Expense(
                    description=expense_data['description'],
                    amount=float(expense_data['amount']),
                    category=expense_data.get('category', 'أخرى'),
                    date=datetime.strptime(expense_data['date'], '%Y-%m-%d') if expense_data.get('date') else datetime.now()
                )
                db.session.add(expense)
            
            db.session.commit()
            return jsonify({'success': True, 'message': 'تم إضافة المصروفات بنجاح'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})
    
    return render_template('admin/bulk_add_expenses.html')

@app.route('/admin/expense_search')
@admin_required
def expense_search():
    """البحث في المصروفات"""
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    expenses_query = Expense.query
    
    if query:
        expenses_query = expenses_query.filter(
            Expense.description.contains(query)
        )
    
    if category:
        expenses_query = expenses_query.filter(Expense.category == category)
    
    if date_from:
        expenses_query = expenses_query.filter(
            Expense.date >= datetime.strptime(date_from, '%Y-%m-%d')
        )
    
    if date_to:
        expenses_query = expenses_query.filter(
            Expense.date <= datetime.strptime(date_to, '%Y-%m-%d')
        )
    
    expenses = expenses_query.order_by(Expense.date.desc()).all()
    
    if request.headers.get('Content-Type') == 'application/json':
        return jsonify({
            'expenses': [{
                'id': expense.id,
                'description': expense.description,
                'amount': expense.amount,
                'category': expense.category,
                'date': expense.date.strftime('%Y-%m-%d')
            } for expense in expenses]
        })
    
    return render_template('admin/expense_search.html', expenses=expenses)

# إصلاح 2: نقل المسارات من أسفل الملف إلى هنا
@app.route('/admin/save_changes', methods=['POST'])
@admin_required
def save_changes():
    """حفظ التغييرات على المشتركين والمدفوعات"""
    try:
        data = request.get_json()
        changes = data.get('changes', [])
        
        for change in changes:
            if change['type'] == 'payment':
                # تحديث حالة الدفع
                payment = Payment.query.filter_by(
                    member_id=change['member_id'],
                    month=change['month'],
                    year=change['year']
                ).first()
                
                if not payment:
                    # إنشاء دفعة جديدة
                    payment = Payment(
                        member_id=change['member_id'],
                        month=change['month'],
                        year=change['year'],
                        amount=1000,
                        is_paid=change['is_paid'],
                        payment_date=datetime.now() if change['is_paid'] else None
                    )
                    db.session.add(payment)
                else:
                    payment.is_paid = change['is_paid']
                    payment.payment_date = datetime.now() if change['is_paid'] else None
                    
            elif change['type'] == 'member':
                # تحديث بيانات المشترك
                member = Member.query.get(change['id'])
                if member:
                    member.name = change['name']
                    member.village = change['village']
                    member.membership_fee = change['membership_fee']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ===== مسارات إدارة المساعدات والمساهمات =====

@app.route("/admin/assistance")
@admin_required
def admin_assistance():
    """إدارة المساعدات والمساهمات"""
    assistances = Assistance.query.order_by(Assistance.date_received.desc()).all()
    
    # حساب إجمالي المساعدات
    total_assistance = sum(assistance.amount for assistance in assistances)
    
    # تصنيف المساعدات حسب النوع
    assistance_by_type = {}
    for assistance in assistances:
        if assistance.assistance_type not in assistance_by_type:
            assistance_by_type[assistance.assistance_type] = []
        assistance_by_type[assistance.assistance_type].append(assistance)
    
    return render_template('admin/assistance_manage.html', 
                         assistances=assistances,
                         total_assistance=total_assistance,
                         assistance_by_type=assistance_by_type)

@app.route("/admin/assistance/add", methods=['POST'])
@admin_required
def add_assistance():
    """إضافة مساعدة جديدة"""
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        source = request.form.get('source')
        assistance_type = request.form.get('assistance_type')
        amount = float(request.form.get('amount', 0))
        notes = request.form.get('notes')
        
        assistance = Assistance(
            title=title,
            description=description,
            source=source,
            assistance_type=assistance_type,
            amount=amount,
            notes=notes
        )
        
        db.session.add(assistance)
        
        # إضافة المساعدة كأصل إذا كانت من نوع أصول ثابتة
        if assistance_type == 'أصول ثابتة':
            asset = Asset(
                name=title,
                description=description,
                category='مساعدات',
                purchase_value=amount,
                current_value=amount,
                status='فعال',
                notes=f'مساعدة من {source}'
            )
            db.session.add(asset)
        
        db.session.commit()
        flash('تم إضافة المساعدة بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في إضافة المساعدة: {str(e)}', 'error')
    
    return redirect(url_for('admin_assistance'))

@app.route("/admin/assistance/edit/<int:assistance_id>", methods=['POST'])
@admin_required
def edit_assistance(assistance_id):
    """تعديل مساعدة"""
    try:
        assistance = Assistance.query.get_or_404(assistance_id)
        
        assistance.title = request.form.get('title')
        assistance.description = request.form.get('description')
        assistance.source = request.form.get('source')
        assistance.assistance_type = request.form.get('assistance_type')
        assistance.amount = float(request.form.get('amount', 0))
        assistance.notes = request.form.get('notes')
        assistance.status = request.form.get('status')
        
        db.session.commit()
        flash('تم تحديث المساعدة بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في تحديث المساعدة: {str(e)}', 'error')
    
    return redirect(url_for('admin_assistance'))

@app.route("/admin/assistance/delete/<int:assistance_id>", methods=['POST'])
@admin_required
def delete_assistance(assistance_id):
    """حذف مساعدة"""
    try:
        assistance = Assistance.query.get_or_404(assistance_id)
        db.session.delete(assistance)
        db.session.commit()
        flash('تم حذف المساعدة بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في حذف المساعدة: {str(e)}', 'error')
    
    return redirect(url_for('admin_assistance'))

@app.route("/admin/assistance/report")
@admin_required
def assistance_report():
    """تقرير المساعدات"""
    assistances = Assistance.query.order_by(Assistance.date_received.desc()).all()
    
    # إحصائيات المساعدات
    stats = {
        'total_count': len(assistances),
        'total_amount': sum(assistance.amount for assistance in assistances),
        'by_type': {},
        'by_source': {},
        'by_year': {}
    }
    
    for assistance in assistances:
        # حسب النوع
        if assistance.assistance_type not in stats['by_type']:
            stats['by_type'][assistance.assistance_type] = {'count': 0, 'amount': 0}
        stats['by_type'][assistance.assistance_type]['count'] += 1
        stats['by_type'][assistance.assistance_type]['amount'] += assistance.amount
        
        # حسب المصدر
        if assistance.source not in stats['by_source']:
            stats['by_source'][assistance.source] = {'count': 0, 'amount': 0}
        stats['by_source'][assistance.source]['count'] += 1
        stats['by_source'][assistance.source]['amount'] += assistance.amount
        
        # حسب السنة
        year = assistance.date_received.year
        if year not in stats['by_year']:
            stats['by_year'][year] = {'count': 0, 'amount': 0}
        stats['by_year'][year]['count'] += 1
        stats['by_year'][year]['amount'] += assistance.amount
    
    return render_template('admin/assistance_report.html', 
                         assistances=assistances, 
                         stats=stats)


# ===== مسارات إدارة التوالف =====

@app.route("/admin/spoilage")
@admin_required
def admin_spoilage():
    """إدارة التوالف (مخفية عن الزوار)"""
    spoilages = Spoilage.query.order_by(Spoilage.spoilage_date.desc()).all()
    
    # حساب إجمالي التوالف
    total_spoilage = sum(spoilage.spoilage_value for spoilage in spoilages)
    total_original = sum(spoilage.original_value for spoilage in spoilages)
    
    # تصنيف التوالف حسب الفئة
    spoilage_by_category = {}
    for spoilage in spoilages:
        if spoilage.category not in spoilage_by_category:
            spoilage_by_category[spoilage.category] = []
        spoilage_by_category[spoilage.category].append(spoilage)
    
    return render_template('admin/spoilage_manage.html', 
                         spoilages=spoilages,
                         total_spoilage=total_spoilage,
                         total_original=total_original,
                         spoilage_by_category=spoilage_by_category)

@app.route("/admin/spoilage/add", methods=['POST'])
@admin_required
def add_spoilage():
    """إضافة تلف جديد"""
    try:
        item_name = request.form.get('item_name')
        description = request.form.get('description')
        original_value = float(request.form.get('original_value', 0))
        spoilage_value = float(request.form.get('spoilage_value', 0))
        spoilage_reason = request.form.get('spoilage_reason')
        category = request.form.get('category')
        notes = request.form.get('notes')
        
        spoilage = Spoilage(
            item_name=item_name,
            description=description,
            original_value=original_value,
            spoilage_value=spoilage_value,
            spoilage_reason=spoilage_reason,
            category=category,
            notes=notes
        )
        
        db.session.add(spoilage)
        
        # تحديث قيمة الأصل المقابل إذا وجد
        asset = Asset.query.filter_by(name=item_name).first()
        if asset:
            asset.current_value = max(0, asset.current_value - spoilage_value)
            if asset.current_value == 0:
                asset.status = 'تالف'
        
        db.session.commit()
        flash('تم إضافة التلف بنجاح وخصمه من الأصول', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في إضافة التلف: {str(e)}', 'error')
    
    return redirect(url_for('admin_spoilage'))

@app.route("/admin/spoilage/edit/<int:spoilage_id>", methods=['POST'])
@admin_required
def edit_spoilage(spoilage_id):
    """تعديل تلف"""
    try:
        spoilage = Spoilage.query.get_or_404(spoilage_id)
        old_value = spoilage.spoilage_value
        
        spoilage.item_name = request.form.get('item_name')
        spoilage.description = request.form.get('description')
        spoilage.original_value = float(request.form.get('original_value', 0))
        spoilage.spoilage_value = float(request.form.get('spoilage_value', 0))
        spoilage.spoilage_reason = request.form.get('spoilage_reason')
        spoilage.category = request.form.get('category')
        spoilage.notes = request.form.get('notes')
        spoilage.status = request.form.get('status')
        
        # تحديث قيمة الأصل المقابل
        asset = Asset.query.filter_by(name=spoilage.item_name).first()
        if asset:
            # إعادة القيمة القديمة وخصم الجديدة
            asset.current_value += old_value
            asset.current_value = max(0, asset.current_value - spoilage.spoilage_value)
            if asset.current_value == 0:
                asset.status = 'تالف'
            elif spoilage.status == 'مُصلح':
                asset.status = 'فعال'
        
        db.session.commit()
        flash('تم تحديث التلف بنجاح', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في تحديث التلف: {str(e)}', 'error')
    
    return redirect(url_for('admin_spoilage'))

@app.route("/admin/spoilage/delete/<int:spoilage_id>", methods=['POST'])
@admin_required
def delete_spoilage(spoilage_id):
    """حذف تلف"""
    try:
        spoilage = Spoilage.query.get_or_404(spoilage_id)
        
        # إعادة القيمة للأصل المقابل
        asset = Asset.query.filter_by(name=spoilage.item_name).first()
        if asset:
            asset.current_value += spoilage.spoilage_value
            if asset.status == 'تالف' and asset.current_value > 0:
                asset.status = 'فعال'
        
        db.session.delete(spoilage)
        db.session.commit()
        flash('تم حذف التلف بنجاح وإعادة قيمته للأصول', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'حدث خطأ في حذف التلف: {str(e)}', 'error')
    
    return redirect(url_for('admin_spoilage'))

@app.route("/admin/spoilage/report")
@admin_required
def spoilage_report():
    """تقرير التوالف"""
    spoilages = Spoilage.query.order_by(Spoilage.spoilage_date.desc()).all()
    
    # إحصائيات التوالف
    stats = {
        'total_count': len(spoilages),
        'total_original': sum(spoilage.original_value for spoilage in spoilages),
        'total_spoilage': sum(spoilage.spoilage_value for spoilage in spoilages),
        'by_category': {},
        'by_reason': {},
        'by_year': {}
    }
    
    for spoilage in spoilages:
        # حسب الفئة
        if spoilage.category not in stats['by_category']:
            stats['by_category'][spoilage.category] = {'count': 0, 'value': 0}
        stats['by_category'][spoilage.category]['count'] += 1
        stats['by_category'][spoilage.category]['value'] += spoilage.spoilage_value
        
        # حسب السبب
        if spoilage.spoilage_reason not in stats['by_reason']:
            stats['by_reason'][spoilage.spoilage_reason] = {'count': 0, 'value': 0}
        stats['by_reason'][spoilage.spoilage_reason]['count'] += 1
        stats['by_reason'][spoilage.spoilage_reason]['value'] += spoilage.spoilage_value
        
        # حسب السنة
        year = spoilage.spoilage_date.year
        if year not in stats['by_year']:
            stats['by_year'][year] = {'count': 0, 'value': 0}
        stats['by_year'][year]['count'] += 1
        stats['by_year'][year]['value'] += spoilage.spoilage_value
    
    # حساب نسبة التلف
    stats['spoilage_percentage'] = (stats['total_spoilage'] / stats['total_original'] * 100) if stats['total_original'] > 0 else 0
    
    return render_template('admin/spoilage_report.html', 
                         spoilages=spoilages, 
                         stats=stats)

# ===== مسارات إدارة الأصول =====

@app.route("/admin/assets")
@admin_required
def admin_assets():
    """إدارة الأصول"""
    assets = Asset.query.order_by(Asset.purchase_date.desc()).all()
    
    # حساب إجمالي الأصول
    total_purchase_value = sum(asset.purchase_value for asset in assets)
    total_current_value = sum(asset.get_current_value() for asset in assets)
    total_depreciation = total_purchase_value - total_current_value
    
    return render_template('admin/assets_manage.html', 
                         assets=assets,
                         total_purchase_value=total_purchase_value,
                         total_current_value=total_current_value,
                         total_depreciation=total_depreciation)

# إصلاح 3: إضافة المسارات الناقصة لمنع الأخطاء
@app.route('/export/members')
@admin_required
def export_members_excel():
    # يمكنك إضافة منطق تصدير اكسل هنا لاحقاً
    flash('ميزة التصدير إلى Excel قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_members'))

@app.route('/export/expenses')
@admin_required
def export_expenses_excel():
    # يمكنك إضافة منطق تصدير اكسل هنا لاحقاً
    flash('ميزة التصدير إلى Excel قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_expenses'))

@app.route('/admin/edit_project/<int:project_id>', methods=['POST'])
@admin_required
def edit_project(project_id):
    # يمكنك إضافة منطق تعديل المشروع هنا لاحقاً
    flash('ميزة تعديل المشروع قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_projects'))

@app.route('/export/members_word')
@admin_required
def export_members_word():
    """تصدير قائمة الأعضاء إلى ملف Word (قيد التطوير)"""
    flash('ميزة التصدير إلى Word قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_dashboard'))

# ===== إضافة المسارات الناقصة من لوحة التحكم =====

@app.route('/export/members_pdf')
@admin_required
def export_members_pdf():
    flash('ميزة تصدير PDF قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/export/payments_report')
@admin_required
def export_payments_report():
    flash('ميزة تقرير المدفوعات قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/export/expenses_report')
@admin_required
def export_expenses_report():
    flash('ميزة تقرير المصروفات قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/upload_excel', methods=['POST'])
@admin_required
def upload_excel():
    flash('ميزة رفع ملف Excel قيد التطوير حالياً.', 'info')
    return redirect(url_for('admin_dashboard'))


# يجب أن يكون هذا الجزء هو آخر شيء في الملف
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)