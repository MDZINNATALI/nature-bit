from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    orders = db.relationship('Order', backref='customer', lazy=True)
    cart_items = db.relationship('Cart', backref='user', lazy=True)

class Plant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    scientific_name = db.Column(db.String(200))
    category = db.Column(db.String(100))
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    old_price = db.Column(db.Float, default=0)
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(500))
    featured = db.Column(db.Boolean, default=False)
    
    # গাছের বিশেষ বৈশিষ্ট্য
    light_requirement = db.Column(db.String(100))
    water_requirement = db.Column(db.String(100))
    height = db.Column(db.String(50))
    pot_size = db.Column(db.String(50))
    blooming_season = db.Column(db.String(100))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    cart_items = db.relationship('Cart', backref='plant', lazy=True)
    order_items = db.relationship('OrderItem', backref='plant', lazy=True)

class Cart(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    total_amount = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, default=0)
    delivery_charge = db.Column(db.Float, default=0)
    final_amount = db.Column(db.Float, nullable=False)
    
    delivery_address = db.Column(db.Text, nullable=False)
    delivery_phone = db.Column(db.String(20), nullable=False)
    delivery_date = db.Column(db.DateTime)
    delivery_time = db.Column(db.String(50))
    
    payment_method = db.Column(db.String(50))
    payment_status = db.Column(db.String(50), default='pending')
    transaction_id = db.Column(db.String(100))
    
    status = db.Column(db.String(50), default='pending')
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    plant_name = db.Column(db.String(200))
    price = db.Column(db.Float)
    quantity = db.Column(db.Integer)
    total = db.Column(db.Float)

class OfflineSale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), unique=True)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    customer_address = db.Column(db.Text)
    source = db.Column(db.String(50), default='facebook')
    
    total_amount = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, default=0)
    delivery_charge = db.Column(db.Float, default=0)
    final_amount = db.Column(db.Float, nullable=False)
    
    payment_method = db.Column(db.String(50))
    payment_number = db.Column(db.String(50))
    transaction_id = db.Column(db.String(100))
    payment_status = db.Column(db.String(50), default='paid')
    
    delivery_status = db.Column(db.String(50), default='pending')
    delivery_date = db.Column(db.DateTime)
    
    notes = db.Column(db.Text)
    sold_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    items = db.relationship('OfflineSaleItem', backref='sale', lazy=True)

class OfflineSaleItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('offline_sale.id'), nullable=False)
    plant_id = db.Column(db.Integer, db.ForeignKey('plant.id'), nullable=False)
    plant_name = db.Column(db.String(200))
    price = db.Column(db.Float)
    quantity = db.Column(db.Integer)
    total = db.Column(db.Float)