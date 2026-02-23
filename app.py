from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import os
import random
import string
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import time
from werkzeug.utils import secure_filename

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin
from flask_bcrypt import Bcrypt
from extensions import db, bcrypt, login_manager
from models import User, Plant, Cart, Order, OrderItem, OfflineSale, OfflineSaleItem, ContactMessage

app = Flask(__name__)

# ✅ Detect Vercel
is_vercel = (os.getenv("VERCEL") is not None) or (os.getenv("VERCEL_ENV") is not None)

# ✅ Database config
# ---------------------------
if is_vercel:
    db_url = os.environ.get("DATABASE_URL")

    # ✅ যদি Postgres না থাকে → SQLite fallback (/tmp only)
    if not db_url:
        os.makedirs("/tmp", exist_ok=True)  # ✅ এখানে দরকার
        db_url = "sqlite:////tmp/nature_bit.db"

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nature_bit.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ---------------------------
# ✅ Init extensions (সবচেয়ে important)
# ---------------------------
db.init_app(app)
bcrypt.init_app(app)
login_manager.init_app(app)
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------------------
# ✅ Create tables (app_context এর ভিতর)
# ---------------------------
with app.app_context():
    db.create_all()

    # ✅ Optional: admin auto-create (LOCAL এ রাখাই ভালো)
    if not is_vercel:
        admin_user = User.query.filter_by(username="admin").first()
        if not admin_user:
            admin = User(
                username="admin",
                email="admin@naturebit.com",
                password_hash=bcrypt.generate_password_hash("admin123").decode("utf-8"),
                phone="01700000000",
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created: admin / admin123")

# ---------------------------
# ✅ Helpers (must be before routes)
# ---------------------------

def generate_order_number():
    # উদাহরণ: ORD-20260223-8K3P1Z
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{date_part}-{rand_part}"


def generate_sale_number():
    # উদাহরণ: SALE-20260223-5QX2A9
    date_part = datetime.now().strftime("%Y%m%d")
    rand_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"SALE-{date_part}-{rand_part}"


def save_plant_image(image_file):
    """
    Upload folder এ image save করবে।
    Vercel এ filesystem read-only, শুধু /tmp writable, তাই Vercel এ /tmp ব্যবহার করা হবে।
    """
    if not image_file or image_file.filename == "":
        return None

    filename = secure_filename(image_file.filename)
    ext = os.path.splitext(filename)[1].lower()
    allowed = {".png", ".jpg", ".jpeg", ".webp"}

    if ext not in allowed:
        raise ValueError("Only png/jpg/jpeg/webp allowed")

    # unique নাম
    unique = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    filename = f"plant_{int(time.time())}_{unique}{ext}"

    # Vercel হলে /tmp, না হলে local uploads folder
    base_dir = "/tmp/uploads" if is_vercel else os.path.join(app.root_path, "static", "uploads")
    os.makedirs(base_dir, exist_ok=True)

    save_path = os.path.join(base_dir, filename)
    image_file.save(save_path)

    # template এ দেখানোর জন্য static path return করা ভালো (local এ)
    # কিন্তু Vercel এ /tmp ফাইল public হবে না (এটা limitation) — prod এ image CDN/Cloudinary দরকার
    return filename

# Local static uploads folder (templates will use /static/uploads/<filename>)
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")



@app.route("/")
def index():
    featured_plants = Plant.query.filter_by(featured=True).limit(12).all()
    new_plants = Plant.query.order_by(Plant.created_at.desc()).limit(12).all()
    categories = db.session.query(Plant.category).distinct().all()
    return render_template(
        "index.html",
        featured_plants=featured_plants,
        new_plants=new_plants,
        categories=categories
    )


# ========== গাছের ক্যাটালগ ==========
@app.route('/plants')
def plants():
    category = request.args.get('category', 'all')
    search = request.args.get('search', '')
    min_price = request.args.get('min_price', '')
    max_price = request.args.get('max_price', '')
    
    query = Plant.query
    
    if category != 'all':
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Plant.name.contains(search) | 
                           Plant.scientific_name.contains(search))
    if min_price:
        query = query.filter(Plant.price >= float(min_price))
    if max_price:
        query = query.filter(Plant.price <= float(max_price))
    
    plants = query.order_by(Plant.created_at.desc()).all()
    categories = db.session.query(Plant.category).distinct().all()
    
    return render_template('plants.html', 
                         plants=plants, 
                         categories=categories,
                         current_category=category)

@app.route('/plant/<int:id>')
def plant_detail(id):
    plant = Plant.query.get_or_404(id)
    related = Plant.query.filter_by(category=plant.category).filter(Plant.id != id).limit(4).all()
    return render_template('plant_detail.html', plant=plant, related=related)

# ========== ইউজার রেজিস্ট্রেশন ==========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        
        if User.query.filter_by(username=username).first():
            flash('এই ইউজারনেম ইতিমধ্যে আছে')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('এই ইমেইল ইতিমধ্যে আছে')
            return redirect(url_for('register'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, phone=phone, password_hash=hashed_password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('রেজিস্ট্রেশন সফল! এখন লগইন করুন')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# ========== লগইন ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f'স্বাগতম {user.username}!')
            return redirect(url_for('index'))
        else:
            flash('ভুল ইউজারনেম বা পাসওয়ার্ড')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('আপনি লগআউট করেছেন')
    return redirect(url_for('index'))

# ========== কার্ট সিস্টেম ==========
@app.route('/add-to-cart/<int:plant_id>', methods=['POST'])
@login_required
def add_to_cart(plant_id):
    plant = Plant.query.get_or_404(plant_id)
    quantity = int(request.form.get('quantity', 1))
    
    if plant.stock < quantity:
        flash(f'স্টকে মাত্র {plant.stock}টি আছে')
        return redirect(url_for('plant_detail', id=plant_id))
    
    cart_item = Cart.query.filter_by(user_id=current_user.id, plant_id=plant_id).first()
    
    if cart_item:
        new_qty = cart_item.quantity + quantity
        if new_qty <= plant.stock:
            cart_item.quantity = new_qty
            flash(f'পরিমাণ {new_qty} করা হয়েছে')
        else:
            flash(f'স্টক সীমা অতিক্রম! মাত্র {plant.stock}টি নিতে পারেন')
    else:
        cart_item = Cart(user_id=current_user.id, plant_id=plant_id, quantity=quantity)
        db.session.add(cart_item)
        flash(f'{quantity}টি কার্টে যোগ হয়েছে')
    
    db.session.commit()
    return redirect(url_for('cart'))

@app.route('/cart')
@login_required
def cart():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    subtotal = sum(item.plant.price * item.quantity for item in cart_items)
    delivery_charge = 60 if subtotal < 500 else 0
    total = subtotal + delivery_charge
    
    return render_template('cart.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_charge=delivery_charge,
                         total=total)

@app.route('/update-cart/<int:item_id>', methods=['POST'])
@login_required
def update_cart(item_id):
    cart_item = Cart.query.get_or_404(item_id)
    quantity = int(request.form['quantity'])
    
    if quantity > 0 and quantity <= cart_item.plant.stock:
        cart_item.quantity = quantity
        db.session.commit()
        flash('পরিমাণ আপডেট হয়েছে')
    elif quantity == 0:
        db.session.delete(cart_item)
        db.session.commit()
        flash('গাছ কার্ট থেকে সরানো হয়েছে')
    else:
        flash(f'স্টক সীমা অতিক্রম! মাত্র {cart_item.plant.stock}টি নিতে পারেন')
    
    return redirect(url_for('cart'))

@app.route('/remove-from-cart/<int:item_id>')
@login_required
def remove_from_cart(item_id):
    cart_item = Cart.query.get_or_404(item_id)
    db.session.delete(cart_item)
    db.session.commit()
    flash('গাছ কার্ট থেকে সরানো হয়েছে')
    return redirect(url_for('cart'))

# ========== চেকআউট ==========
@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart_items = Cart.query.filter_by(user_id=current_user.id).all()
    if not cart_items:
        flash('আপনার কার্ট খালি')
        return redirect(url_for('plants'))
    
    subtotal = sum(item.plant.price * item.quantity for item in cart_items)
    delivery_charge = 60 if subtotal < 500 else 0
    total = subtotal + delivery_charge
    
    if request.method == 'POST':
        order = Order(
            order_number=generate_order_number(),
            user_id=current_user.id,
            total_amount=subtotal,
            delivery_charge=delivery_charge,
            final_amount=total,
            delivery_address=request.form['address'],
            delivery_phone=request.form['phone'],
            delivery_date=datetime.strptime(request.form['delivery_date'], '%Y-%m-%d') if request.form.get('delivery_date') else None,
            delivery_time=request.form.get('delivery_time', ''),
            payment_method=request.form['payment_method'],
            notes=request.form.get('notes', ''),
            status='pending',
            payment_status='pending'
        )
        db.session.add(order)
        db.session.flush()
        
        for item in cart_items:
            order_item = OrderItem(
                order_id=order.id,
                plant_id=item.plant_id,
                plant_name=item.plant.name,
                price=item.plant.price,
                quantity=item.quantity,
                total=item.plant.price * item.quantity
            )
            db.session.add(order_item)
            
            item.plant.stock -= item.quantity
            db.session.delete(item)
        
        db.session.commit()
        
        flash('অর্ডার সফল হয়েছে! অর্ডার নম্বর: ' + order.order_number)
        return redirect(url_for('orders'))
    
    user = current_user
    min_date = datetime.now().date()
    max_date = min_date + timedelta(days=7)
    
    return render_template('checkout.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         delivery_charge=delivery_charge,
                         total=total,
                         user=user,
                         min_date=min_date,
                         max_date=max_date)

# ========== অর্ডার ==========
@app.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

@app.route('/order/<int:id>')
@login_required
def order_detail(id):
    order = Order.query.get_or_404(id)
    if order.user_id != current_user.id and not current_user.is_admin:
        flash('আপনি এই অর্ডার দেখতে পারবেন না')
        return redirect(url_for('index'))
    return render_template('order_detail.html', order=order)

# ========== এডমিন রুটস ==========
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('এডমিন এলাকা')
        return redirect(url_for('index'))
    
    total_orders = Order.query.count()
    total_plants = Plant.query.count()
    total_users = User.query.count()
    total_offline_sales = OfflineSale.query.count()
    
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    recent_sales = OfflineSale.query.order_by(OfflineSale.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_orders=total_orders,
                         total_plants=total_plants,
                         total_users=total_users,
                         total_offline_sales=total_offline_sales,
                         recent_orders=recent_orders,
                         recent_sales=recent_sales)

@app.route('/admin/plants')
@login_required
def admin_plants():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    plants = Plant.query.order_by(Plant.created_at.desc()).all()
    return render_template('admin/products.html', plants=plants)

@app.route('/admin/plants/add', methods=['GET', 'POST'])
@login_required
def add_plant():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            image = request.files['image']
            filename = save_plant_image(image) if image else None
            
            # ✅ old_price খালি থাকলে 0 সেট করুন
            old_price_str = request.form.get('old_price', '')
            old_price = float(old_price_str) if old_price_str else 0
            
            plant = Plant(
                name=request.form['name'],
                scientific_name=request.form.get('scientific_name', ''),
                category=request.form['category'],
                description=request.form['description'],
                price=float(request.form['price']),
                old_price=old_price,  # ✅ ফিক্সড
                stock=int(request.form['stock']),
                image=filename,
                featured='featured' in request.form,
                light_requirement=request.form.get('light_requirement', ''),
                water_requirement=request.form.get('water_requirement', ''),
                height=request.form.get('height', ''),
                pot_size=request.form.get('pot_size', ''),
                blooming_season=request.form.get('blooming_season', '')
            )
            
            db.session.add(plant)
            db.session.commit()
            flash('গাছ যোগ হয়েছে')
            return redirect(url_for('admin_plants'))
            
        except Exception as e:
            print(f"Error: {e}")
            flash(f'গাছ যোগ করতে সমস্যা: {str(e)}')
            return redirect(url_for('add_plant'))
    
    return render_template('admin/add_product.html')

@app.route('/admin/plants/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_plant(id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    plant = Plant.query.get_or_404(id)
    
    if request.method == 'POST':
        plant.name = request.form['name']
        plant.scientific_name = request.form.get('scientific_name', '')
        plant.category = request.form['category']
        plant.description = request.form['description']
        plant.price = float(request.form['price'])
        plant.old_price = float(request.form.get('old_price', 0))
        plant.stock = int(request.form['stock'])
        plant.featured = 'featured' in request.form
        plant.light_requirement = request.form.get('light_requirement', '')
        plant.water_requirement = request.form.get('water_requirement', '')
        plant.height = request.form.get('height', '')
        plant.pot_size = request.form.get('pot_size', '')
        plant.blooming_season = request.form.get('blooming_season', '')
        
        image = request.files['image']
        if image:
            if plant.image:
                old_file = os.path.join(app.config['UPLOAD_FOLDER'], plant.image)
                if os.path.exists(old_file):
                    os.remove(old_file)
            plant.image = save_plant_image(image)
        
        db.session.commit()
        flash('গাছ আপডেট হয়েছে')
        return redirect(url_for('admin_plants'))
    
    return render_template('admin/edit_product.html', plant=plant)

@app.route('/admin/plants/delete/<int:id>')
@login_required
def delete_plant(id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    plant = Plant.query.get_or_404(id)
    
    if plant.image:
        old_file = os.path.join(app.config['UPLOAD_FOLDER'], plant.image)
        if os.path.exists(old_file):
            os.remove(old_file)
    
    db.session.delete(plant)
    db.session.commit()
    flash('গাছ ডিলিট হয়েছে')
    return redirect(url_for('admin_plants'))

@app.route('/admin/orders')
@login_required
def admin_orders():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders)

@app.route('/admin/orders/update/<int:id>', methods=['POST'])
@login_required
def update_order_status(id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    order = Order.query.get_or_404(id)
    order.status = request.form['status']
    
    if 'tracking_number' in request.form:
        order.tracking_number = request.form['tracking_number']
    
    db.session.commit()
    flash('অর্ডার স্ট্যাটাস আপডেট হয়েছে')
    return redirect(url_for('admin_orders'))

@app.route('/admin/offline-sales')
@login_required
def offline_sales():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    sales = OfflineSale.query.order_by(OfflineSale.created_at.desc()).all()
    return render_template('admin/offline_sales.html', sales=sales)

@app.route('/admin/offline-sales/add', methods=['GET', 'POST'])
@login_required
def add_offline_sale():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        customer_name = request.form['customer_name']
        customer_phone = request.form['customer_phone']
        customer_address = request.form.get('customer_address', '')
        source = request.form.get('source', 'facebook')
        payment_method = request.form['payment_method']
        payment_number = request.form.get('payment_number', '')
        transaction_id = request.form.get('transaction_id', '')
        
        plant_ids = request.form.getlist('plant_id[]')
        quantities = request.form.getlist('quantity[]')
        prices = request.form.getlist('price[]')
        
        total = 0
        items = []
        sale_number = generate_sale_number()
        
        for i in range(len(plant_ids)):
            if not plant_ids[i] or not quantities[i]:
                continue
            
            plant = Plant.query.get(int(plant_ids[i]))
            qty = int(quantities[i])
            price = float(prices[i]) if prices[i] else plant.price
            
            if plant.stock < qty:
                flash(f'{plant.name} - স্টক মাত্র {plant.stock}টি')
                return redirect(url_for('add_offline_sale'))
            
            item_total = price * qty
            total += item_total
            items.append((plant, qty, price, item_total))
        
        discount = float(request.form.get('discount', 0))
        delivery_charge = float(request.form.get('delivery_charge', 0))
        final = total - discount + delivery_charge
        
        sale = OfflineSale(
            sale_number=sale_number,
            customer_name=customer_name,
            customer_phone=customer_phone,
            customer_address=customer_address,
            source=source,
            total_amount=total,
            discount_amount=discount,
            delivery_charge=delivery_charge,
            final_amount=final,
            payment_method=payment_method,
            payment_number=payment_number,
            transaction_id=transaction_id,
            notes=request.form.get('notes', ''),
            sold_by=current_user.id
        )
        db.session.add(sale)
        db.session.flush()
        
        for plant, qty, price, item_total in items:
            item = OfflineSaleItem(
                sale_id=sale.id,
                plant_id=plant.id,
                plant_name=plant.name,
                price=price,
                quantity=qty,
                total=item_total
            )
            db.session.add(item)
            plant.stock -= qty
        
        db.session.commit()
        flash(f'বিক্রয় #{sale_number} যোগ হয়েছে!')
        return redirect(url_for('offline_sales'))
    
    plants = Plant.query.filter(Plant.stock > 0).all()
    return render_template('admin/add_offline_sale.html', plants=plants)

@app.route('/admin/daily-sales')
@login_required
def daily_sales():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    start_date = request.args.get('start', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    online_orders = Order.query.filter(Order.created_at.between(start, end)).all()
    offline_sales = OfflineSale.query.filter(OfflineSale.created_at.between(start, end)).all()
    
    online_total = sum(o.final_amount for o in online_orders)
    offline_total = sum(o.final_amount for o in offline_sales)
    
    return render_template('admin/daily_sales.html',
                         start_date=start_date,
                         end_date=end_date,
                         online_orders=online_orders,
                         offline_sales=offline_sales,
                         online_total=online_total,
                         offline_total=offline_total,
                         grand_total=online_total+offline_total)

@app.route('/admin/export-sales/<format>')
@login_required
def export_sales(format):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    start_date = request.args.get('start', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
    
    online_orders = Order.query.filter(Order.created_at.between(start, end)).all()
    offline_sales = OfflineSale.query.filter(OfflineSale.created_at.between(start, end)).all()
    
    data = []
    
    for order in online_orders:
        data.append({
            'তারিখ': order.created_at.strftime('%Y-%m-%d'),
            'টাইপ': 'অনলাইন',
            'অর্ডার #': order.order_number,
            'গ্রাহক': order.customer.username,
            'ফোন': order.delivery_phone,
            'মোট': order.total_amount,
            'ডেলিভারি': order.delivery_charge,
            'সর্বমোট': order.final_amount,
            'পেমেন্ট': order.payment_method,
            'স্ট্যাটাস': order.status
        })
    
    for sale in offline_sales:
        data.append({
            'তারিখ': sale.created_at.strftime('%Y-%m-%d'),
            'টাইপ': 'অফলাইন',
            'অর্ডার #': sale.sale_number,
            'গ্রাহক': sale.customer_name,
            'ফোন': sale.customer_phone,
            'মোট': sale.total_amount,
            'ডেলিভারি': sale.delivery_charge,
            'সর্বমোট': sale.final_amount,
            'পেমেন্ট': sale.payment_method,
            'স্ট্যাটাস': sale.delivery_status
        })
    
    df = pd.DataFrame(data)
    filename = f'sales_report_{start_date}_to_{end_date}'
    
    if format == 'excel':
        filepath = os.path.join(app.config['REPORT_FOLDER'], f'{filename}.xlsx')
        df.to_excel(filepath, index=False)
        return send_file(filepath, as_attachment=True)
    
    elif format == 'pdf':
        filepath = os.path.join(app.config['REPORT_FOLDER'], f'{filename}.pdf')
        
        doc = SimpleDocTemplate(filepath, pagesize=landscape(A4))
        elements = []
        styles = getSampleStyleSheet()
        
        title = Paragraph(f"বিক্রয় রিপোর্ট ({start_date} থেকে {end_date})", styles['Title'])
        elements.append(title)
        elements.append(Spacer(1, 0.2*inch))
        
        table_data = [list(df.columns)] + df.values.tolist()
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.green),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        return send_file(filepath, as_attachment=True)
    
    elif format == 'csv':
        filepath = os.path.join(app.config['REPORT_FOLDER'], f'{filename}.csv')
        df.to_csv(filepath, index=False, encoding='utf-8-sig')
        return send_file(filepath, as_attachment=True)

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)

# ========== Contact Us ==========
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        contact_msg = ContactMessage(
            name=request.form['name'],
            email=request.form['email'],
            phone=request.form.get('phone', ''),
            subject=request.form['subject'],
            message=request.form['message']
        )
        db.session.add(contact_msg)
        db.session.commit()
        flash('আপনার বার্তা পাঠানো হয়েছে!', 'success')
        return redirect(url_for('contact'))
    
    return render_template('contact.html')

# ========== মেইন (Local only) ==========
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # শুধু লোকাল এ seed
        if not is_vercel:
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    email="admin@naturebit.com",
                    password_hash=bcrypt.generate_password_hash("admin123").decode("utf-8"),
                    phone="01700000000",
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                print("✅ এডমিন ইউজার তৈরি হয়েছে: admin / admin123")

            if Plant.query.count() == 0:
                plants = [
                    Plant(
                        name="মনি প্ল্যান্ট",
                        scientific_name="Epipremnum aureum",
                        category="ইনডোর",
                        description="বাতাস বিশুদ্ধকারী, সহজে বাঁচে",
                        price=350,
                        old_price=450,
                        stock=15,
                        light_requirement="আংশিক ছায়া",
                        water_requirement="মাঝারি",
                        height="২-৩ ফুট",
                        featured=True
                    ),
                    Plant(
                        name="গোলাপ",
                        scientific_name="Rosa",
                        category="ফুল",
                        description="সুগন্ধি ফুল, বাগানের রানী",
                        price=250,
                        stock=10,
                        light_requirement="পূর্ণ সূর্য",
                        water_requirement="নিয়মিত",
                        blooming_season="বসন্ত-শরৎ",
                        featured=True
                    ),
                    Plant(
                        name="অ্যালোভেরা",
                        scientific_name="Aloe vera",
                        category="ঔষধি",
                        description="ত্বকের যত্নে, রসে ভরপুর",
                        price=180,
                        stock=20,
                        light_requirement="পূর্ণ সূর্য",
                        water_requirement="কম",
                        featured=True
                    ),
                ]
                db.session.add_all(plants)
                db.session.commit()
                print("✅ স্যাম্পল গাছ যোগ হয়েছে")

    # ✅ local server run only
    app.run(host="0.0.0.0", port=5000, debug=True)