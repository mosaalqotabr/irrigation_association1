import pandas as pd
import numpy as np
from datetime import datetime
from models import db, Member, Payment
import os

class ExcelManager:
    """مدير العمليات المتعلقة بملفات Excel"""
    
    @staticmethod
    def import_from_excel(file_path):
        """استيراد البيانات من ملف Excel"""
        try:
            # قراءة الملف
            df = pd.read_excel(file_path)
            
            # تنظيف أسماء الأعمدة
            df.columns = df.columns.str.strip()
            
            imported_count = 0
            updated_count = 0
            
            for index, row in df.iterrows():
                # تجاهل الصفوف التي تحتوي على الإجماليات
                if pd.isna(row.get('الرقم')) or str(row.get('الاســـــــــــم', '')).startswith('الجمالــــــــــــــــــــــــــي'):
                    continue
                
                member_number = int(row['الرقم'])
                name = str(row['الاســـــــــــم']).strip()
                membership_fee = float(row.get('رسوم العضوية', 5000))
                notes = str(row.get('Unnamed: 12', '')).strip() if pd.notna(row.get('Unnamed: 12')) else None
                
                # البحث عن العضو أو إنشاؤه
                member = Member.query.filter_by(member_number=member_number).first()
                if not member:
                    member = Member(
                        member_number=member_number,
                        name=name,
                        membership_fee=membership_fee,
                        notes=notes
                    )
                    db.session.add(member)
                    imported_count += 1
                else:
                    member.name = name
                    member.membership_fee = membership_fee
                    member.notes = notes
                    updated_count += 1
                
                # معالجة المدفوعات الشهرية
                months_mapping = {
                    'شهر11 ': (11, 2024),
                    'شهر12 ': (12, 2024),
                    'شهر 1': (1, 2025),
                    'شهر2': (2, 2025),
                    'شهر 3': (3, 2025),
                    'شهر 4': (4, 2025),
                    'شهر 5': (5, 2025),
                    'شهر 6': (6, 2025),
                    'شهر7': (7, 2025)
                }
                
                for col_name, (month, year) in months_mapping.items():
                    if col_name in row and pd.notna(row[col_name]):
                        amount = float(row[col_name])
                        is_paid = amount > 0
                        
                        # البحث عن الدفعة أو إنشاؤها
                        payment = Payment.query.filter_by(
                            member_id=member.id,
                            month=month,
                            year=year
                        ).first()
                        
                        if not payment:
                            payment = Payment(
                                member_id=member.id,
                                month=month,
                                year=year,
                                amount=amount if is_paid else 1000,
                                is_paid=is_paid,
                                payment_date=datetime.now() if is_paid else None
                            )
                            db.session.add(payment)
                        else:
                            payment.amount = amount if is_paid else 1000
                            payment.is_paid = is_paid
                            payment.payment_date = datetime.now() if is_paid else None
            
            db.session.commit()
            return {
                'success': True,
                'imported': imported_count,
                'updated': updated_count,
                'message': f'تم استيراد {imported_count} عضو جديد وتحديث {updated_count} عضو موجود'
            }
            
        except Exception as e:
            db.session.rollback()
            return {
                'success': False,
                'message': f'خطأ في الاستيراد: {str(e)}'
            }
    
    @staticmethod
    def export_to_excel(file_path=None):
        """تصدير البيانات إلى ملف Excel"""
        try:
            members = Member.query.order_by(Member.member_number).all()
            
            # إعداد البيانات للتصدير
            data = []
            
            for member in members:
                row = {
                    'الرقم': member.member_number,
                    'الاســـــــــــم': member.name,
                    'رسوم العضوية': member.membership_fee
                }
                
                # إضافة المدفوعات الشهرية
                months_mapping = [
                    ('شهر11 ', 11, 2024),
                    ('شهر12 ', 12, 2024),
                    ('شهر 1', 1, 2025),
                    ('شهر2', 2, 2025),
                    ('شهر 3', 3, 2025),
                    ('شهر 4', 4, 2025),
                    ('شهر 5', 5, 2025),
                    ('شهر 6', 6, 2025),
                    ('شهر7', 7, 2025)
                ]
                
                for col_name, month, year in months_mapping:
                    payment = member.get_payment_for_month(month, year)
                    if payment:
                        row[col_name] = payment.amount if payment.is_paid else 0
                    else:
                        row[col_name] = 0
                
                # إضافة الملاحظات
                row['ملاحظات'] = member.notes or ''
                
                data.append(row)
            
            # إنشاء DataFrame
            df = pd.DataFrame(data)
            
            # إضافة صف الإجماليات
            totals_row = {'الاســـــــــــم': 'الجمالــــــــــــــــــــــــــي'}
            
            for col in df.columns:
                if col.startswith('شهر') or col == 'رسوم العضوية':
                    totals_row[col] = df[col].sum()
                elif col not in ['الرقم', 'الاســـــــــــم', 'ملاحظات']:
                    totals_row[col] = ''
            
            # إضافة صف الإجماليات
            df = pd.concat([df, pd.DataFrame([totals_row])], ignore_index=True)
            
            # حفظ الملف
            if not file_path:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_path = f'تصدير_البيانات_{timestamp}.xlsx'
            
            df.to_excel(file_path, index=False, engine='openpyxl')
            
            return {
                'success': True,
                'file_path': file_path,
                'message': f'تم تصدير {len(members)} عضو بنجاح'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'خطأ في التصدير: {str(e)}'
            }
    
    @staticmethod
    def get_financial_summary():
        """حساب الملخص المالي"""
        try:
            members = Member.query.all()
            
            summary = {
                'total_members': len(members),
                'total_membership_fees': sum(member.membership_fee for member in members),
                'monthly_totals': {},
                'total_collected': 0,
                'total_expected': 0
            }
            
            # حساب المدفوعات الشهرية
            months_mapping = [
                ('شهر11 ', 11, 2024),
                ('شهر12 ', 12, 2024),
                ('شهر 1', 1, 2025),
                ('شهر2', 2, 2025),
                ('شهر 3', 3, 2025),
                ('شهر 4', 4, 2025),
                ('شهر 5', 5, 2025),
                ('شهر 6', 6, 2025),
                ('شهر7', 7, 2025)
            ]
            
            for col_name, month, year in months_mapping:
                monthly_total = 0
                for member in members:
                    payment = member.get_payment_for_month(month, year)
                    if payment and payment.is_paid:
                        monthly_total += payment.amount
                
                summary['monthly_totals'][col_name] = monthly_total
                summary['total_collected'] += monthly_total
            
            # إضافة رسوم العضوية للمجموع
            summary['total_collected'] += summary['total_membership_fees']
            
            # حساب المتوقع (12 شهر × 1000 ريال × عدد الأعضاء + رسوم العضوية)
            summary['total_expected'] = (len(members) * 12 * 1000) + summary['total_membership_fees']
            
            return summary
            
        except Exception as e:
            return {
                'error': f'خطأ في حساب الملخص المالي: {str(e)}'
            }

