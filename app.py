from flask import Flask, request, redirect, url_for, flash, render_template, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash
from sqlalchemy import text
from market_updater import update_market_data
from datetime import datetime
from flask import jsonify
import plotly.graph_objs as go
import plotly.io as pio
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # ✅ Use non-GUI backend
import matplotlib.pyplot as plt
from flask import Response, make_response
import json
from plotly.utils import PlotlyJSONEncoder



app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:satakshi4104@localhost/FinancialPortfolio'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------------- Models ----------------------

class User(db.Model):
    __tablename__ = 'Users'
    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.TIMESTAMP)
    MISCEL = db.Column(db.String(255))

class Portfolio(db.Model):
    __tablename__ = 'Portfolio'
    portfolio_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id'))
    portfolio_name = db.Column(db.String(100))

class Investment(db.Model):
    __tablename__ = 'Investments'
    investment_id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.Integer, db.ForeignKey('Portfolio.portfolio_id'))  # ✅ Fixed here
    asset_id = db.Column(db.Integer)
    quantity = db.Column(db.Numeric(10,2))
    purchase_price = db.Column(db.Numeric(10,2))
    purchase_date = db.Column(db.Date)

class Transaction(db.Model):
    __tablename__ = 'Transactions'
    transaction_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('Users.user_id'))
    asset_id = db.Column(db.Integer)
    transaction_type = db.Column(db.Enum('BUY', 'SELL'))
    quantity = db.Column(db.Numeric(10,2))
    price = db.Column(db.Numeric(10,2))
    transaction_date = db.Column(db.DateTime)

# ✅ Optional (but helpful): define Assets model
class Asset(db.Model):
    __tablename__ = 'Assets'
    asset_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    asset_type = db.Column(db.String(100))
    symbol = db.Column(db.String(20)) 

class MarketData(db.Model):
    __tablename__ = "MarketData"
    market_data_id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("Assets.asset_id"), nullable=False)
    closing_price = db.Column(db.Float, nullable=False)
    volume = db.Column(db.BigInteger, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    asset = db.relationship('Asset', backref=db.backref('market_data', lazy=True))


# ---------------------- Routes ----------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        entered_password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, entered_password):
            session['user_id'] = user.user_id
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "danger")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    user = db.session.get(User, session['user_id'])
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('login'))

    print("Current User:", user.name)  # ✅ Debugging line

    # ✅ Fetch portfolios
    portfolios = db.session.execute(
        text("SELECT * FROM Portfolio WHERE user_id = :uid"),
        {"uid": user.user_id}
    ).mappings().all()

    investments = db.session.execute(
        text("""
            SELECT a.asset_id, a.name, a.asset_type, i.quantity, i.purchase_price, i.purchase_date
            FROM Investments i
            JOIN Assets a ON i.asset_id = a.asset_id
            JOIN Portfolio p ON i.portfolio_id = p.portfolio_id
            WHERE p.user_id = :uid
        """),
        {"uid": user.user_id}
    ).mappings().all()

    total_value = sum(inv['quantity'] * inv['purchase_price'] for inv in investments)

    transactions = db.session.execute(
        text("""
            SELECT t.transaction_type, a.asset_id, a.name, t.quantity, t.quantity * t.price AS amount, t.transaction_date
            FROM Transactions t
            JOIN Assets a ON t.asset_id = a.asset_id
            WHERE t.user_id = :uid
        """),
        {"uid": user.user_id}
    ).mappings().all()

    # ✅ Fetch Market Data
    assets = Asset.query.all()
    market_data = {md.asset_id: md for md in MarketData.query.all()}  

    for asset in assets:
        if asset.asset_id not in market_data:
            market_data[asset.asset_id] = None

    return render_template(
        'dashboard.html',
        user=user,  # ✅ Pass `user` instead of `current_user`
        portfolios=portfolios,
        investments=investments,
        transactions=transactions,
        total_value=round(total_value, 2),
        assets=assets,
        market_data=market_data
    )
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/test')
def test():
    return render_template('login.html')

@app.route('/add_asset', methods=['POST'])
def add_asset():
    if 'user_id' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))

    try:
        name = request.form['name']
        asset_type = request.form['asset_type']
        quantity = float(request.form['quantity'])
        price = float(request.form['purchase_price'])
        purchase_date = request.form['purchase_date']
        symbol = request.form['symbol']
        risk_value = float(request.form['risk_value'])

        user_id = session['user_id']

        # Get user's portfolio
        portfolio = db.session.execute(
            db.text("SELECT * FROM Portfolio WHERE user_id = :uid"),
            {"uid": user_id}
        ).mappings().first()

        # Check if asset already exists in the Assets table
        existing_asset = db.session.execute(
            db.text("SELECT * FROM Assets WHERE symbol = :symbol"),
            {"symbol": symbol}
        ).mappings().first()

        if existing_asset:
            # If asset already exists, use its asset_id
            asset_id = existing_asset['asset_id']
        else:
            # Insert into Assets table if the asset does not exist
            db.session.execute(
                db.text("""
                    INSERT INTO Assets (name, symbol, asset_type, risk_value)
                    VALUES (:name, :symbol, :type, :risk)
                """),
                {"name": name, "symbol": symbol, "type": asset_type, "risk": risk_value}
            )
            asset_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        # Insert into Investments table
        db.session.execute(
            db.text("""
                INSERT INTO Investments (portfolio_id, asset_id, quantity, purchase_price, purchase_date)
                VALUES (:pid, :aid, :qty, :price, :pdate)
            """),
            {
                "pid": portfolio['portfolio_id'],
                "aid": asset_id,
                "qty": quantity,
                "price": price,
                "pdate": purchase_date
            }
        )

        db.session.commit()
        flash("Asset added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        print("❌ Error while adding asset:", e)
        flash("Error adding asset.", "danger")

    return redirect(url_for('dashboard'))
@app.route('/update_market_data', methods=['POST'])
def update_market_data_route():
    try:
        update_market_data(db, MarketData, Asset)  # Call the function
        return jsonify({"message": "Market data updated successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

from flask import Response

from flask import jsonify


@app.route('/performance-metrics/movingAvg/<string:ticker>', methods=['GET'])
def moving_avg(ticker="AAPL", start_date="2024-08-01", end_date="2025-04-01"):
    print(f"Fetching data for {ticker} from {start_date} to {end_date}")
    try:
        data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        print("Downloaded data:", data.shape)

        if data.empty:
            print("⚠️ Data is empty!")
            return Response('{"error": "No data found"}', status=404, mimetype='application/json')

        # Handle multiindex just in case
        if isinstance(data.columns, pd.MultiIndex):
            close_prices = data[('Close', ticker)].copy()
        else:
            close_prices = data['Close'].copy()

        df = pd.DataFrame({'Price': close_prices})
        df['SMA_20'] = df['Price'].rolling(window=20, min_periods=1).mean()
        df['SMA_50'] = df['Price'].rolling(window=50, min_periods=1).mean()
        df['EMA_20'] = df['Price'].ewm(span=20, adjust=False).mean()

        min_val = df[['Price', 'SMA_20', 'SMA_50', 'EMA_20']].min().min()
        max_val = df[['Price', 'SMA_20', 'SMA_50', 'EMA_20']].max().max()
        padding = (max_val - min_val) * 0.1

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df.index, y=df['Price'], name=f"{ticker.upper()} Price",
                                 line=dict(color='royalblue', width=3)))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], name="SMA 20",
                                 line=dict(color='green', width=2, dash='dash')))
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], name="SMA 50",
                                 line=dict(color='red', width=2, dash='dot')))
        fig.add_trace(go.Scatter(x=df.index, y=df['EMA_20'], name="EMA 20",
                                 line=dict(color='gold', width=2)))

        fig.update_layout(
            yaxis=dict(
                range=[min_val - padding, max_val + padding],
                tickformat=".2f",
                fixedrange=False
            ),
            template="plotly_white"
        )
        fig_json = json.dumps(fig, cls=PlotlyJSONEncoder)
        response = make_response(fig_json)
        response.headers['Content-Type'] = 'application/json'
        return response
    
    except Exception as e:
        print("❌ Error in moving_avg():", str(e))
        return Response('{"error": "Server error occurred"}', status=500, mimetype='application/json')
def daily_returns_api(data,ticker):
    start_date = "2024-08-01"
    end_date = "2025-04-01"
    try:
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        if stock_data.empty:
            return Response('{"error": "No data found"}', status=404, mimetype='application/json')

        df = stock_data[["Close"]].copy()
        df["Daily Returns"] = df["Close"].pct_change()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Daily Returns"], mode='lines', name="Daily Returns",
            line=dict(color="purple")
        ))

        fig.update_layout(
            title=f"{ticker.upper()} - Daily Returns",
            xaxis_title="Date",
            yaxis_title="Returns",
            template="plotly_dark"
        )

        fig_json = json.dumps(fig, cls=PlotlyJSONEncoder)
        return Response(fig_json, mimetype='application/json')

    except Exception as e:
        print("❌ Error in daily_returns_api():", str(e))
        return Response('{"error": "Server error occurred"}', status=500, mimetype='application/json')

# 📌 Correlation Analysis
def correlation_analysis(stock_data):
    corr_matrix = stock_data.corr()
    
    fig = go.Figure(data=go.Heatmap(z=corr_matrix.values, x=corr_matrix.columns, y=corr_matrix.index, colorscale="Viridis"))
    fig.update_layout(title="Correlation Analysis", template="plotly_dark")
    
    return pio.to_json(fig)

def risk_analysis(stock_data, ticker):
    try:
        start_date = "2024-08-01"
        end_date = "2025-02-13"  # one day before today
        stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if stock_data.empty:
            return Response('{"error": "No data found"}', status=404, mimetype='application/json')

        df = stock_data[["Close"]].copy()
        df["Rolling Std Dev"] = df["Close"].rolling(window=30).std()

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df.index, y=df["Rolling Std Dev"], mode='lines', name="Volatility",
            line=dict(color="red")
        ))

        fig.update_layout(
            title=f"{ticker.upper()} - Risk Analysis (Rolling Std Dev)",
            xaxis_title="Date",
            yaxis_title="Volatility",
            template="plotly_dark"
        )

        fig_json = json.dumps(fig, cls=PlotlyJSONEncoder)
        response = make_response(fig_json)
        response.headers['Content-Type'] = 'application/json'
        return response

    except Exception as e:
        print("❌ Error in risk_analysis_api():", str(e))
        return Response('{"error": "Server error occurred"}', status=500, mimetype='application/json')

# Flask Routes to Serve Pages
@app.route("/moving_avg")
def moving_averages_page():
    return render_template("moving_avg.html")

@app.route("/daily_returns")
def daily_returns_page():
    return render_template("daily_returns.html")

@app.route("/correlation")
def correlation_page():
    return render_template("correlation.html")

@app.route("/risk_analysis")
def risk_analysis_route():
    return render_template("risk_analysis.html")
# Flask Routes to Return JSON for Charts
@app.route("/performance-metrics/<metric>/<ticker>")
def get_performance_metric(metric, ticker):
    start_date = "2024-11-01"
    end_date = "2025-02-13"  # one day before today
      


    # Correlation might not need the ticker directly
    if metric == "correlation":
        return correlation_analysis()  # Define it accordingly

    # Download stock data
    data = yf.download(ticker, start=start_date, end=end_date, progress=False)

    # Handle missing or malformed data
    if data.empty:
        return jsonify({"error": "No data found for the given ticker."}), 404

    if isinstance(data.columns, pd.MultiIndex):
        # Handle case for multiple tickers (if needed in future)
        close_data = data.xs("Close", axis=1, level=0)
        if ticker not in close_data.columns:
            return jsonify({"error": "Ticker not found in the dataset."}), 404
    else:
        if 'Close' not in data.columns:
            return jsonify({"error": "Invalid data format for ticker."}), 404

    # Route based on metric
    if metric == "movingAvg":
        fig_json = moving_avg(ticker, start_date, end_date)
        return Response(fig_json, mimetype='application/json')

    elif metric == "dailyReturns":
        return daily_returns_api(data, ticker)
    elif metric == "risk":
        return risk_analysis(data, ticker)
    else:
        return jsonify({"error": "Invalid performance metric."}), 400
    
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%d-%m-%Y'):
    if isinstance(value, str):
        value = datetime.strptime(value, "%Y-%m-%d")  # Adjust format if needed
    return value.strftime(format) if value else ""

# ---------------------- Run App ----------------------

if __name__ == '__main__':
    app.run(debug=True)