import functools
import traceback
from datetime import date

from flask import render_template, request, redirect, url_for, flash
from flask_login import logout_user, login_required, current_user, login_user

from application import app, recaptcha
from application.CouponForms import CreateCouponForm
from application.Models.Admin import *
from application.Models.CouponSystem import CouponSystem, FoodIdNotExistsError
from application.Models.Food2 import FoodDao
from application.CreateFoodForm import CreateFoodForm
from application.Models.FileUpload import save_file

# <------------------------- ASHLEE ------------------------------>

# Decorator to only allow admin accounts or guests
from application.Models.Review import ReviewDao, Review


def admin_side(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if isinstance(current_user, Admin) or not current_user.is_authenticated:
            print(current_user)
            return view(*args, **kwargs)
        flash("You need to log out first to access the Admin side.")
        return redirect('/')

    return wrapper


@app.route("/admin")
@app.route("/admin/home", alias=True)
@admin_side
def admin_home():  # ashlee
    return render_template("admin/home.html")


# TOTP Web Client https://totp.danhersam.com/
@app.route("/admin/login", methods=["GET", "POST"])
@admin_side
def admin_login():  # ashlee
    def login_error():
        return redirect("%s?error=1" % url_for("admin_login"))

    if request.method == "POST":
        # That means user submitted login form. Check errors.
        login = Account.check_credentials(request.form["email"],
                                          request.form["password"])
        if login is not None:
            # Check OTP
            if login.check_otp(request.form["otp"]):
                login.authenticate()
                login_user(login)
                return redirect(url_for("admin_home"))
            else:
                flash("Incorrect OTP")
                return render_template("admin/login.html")
        return login_error()
    return render_template("admin/login.html")


@app.route("/admin/register", methods=["GET", "POST"])
@admin_side
def admin_register():  # ashlee
    def reg_error(ex=None):
        if ex is not None:
            if Account.EMAIL_ALREADY_EXISTS in ex.args:
                return redirect("%s?emailExists=1" % url_for("admin_register"))
        # Given js validation, shouldn't reach here by a normal user.
        return redirect("%s?error=1" % url_for("admin_register"))

    if request.method == "POST":
        if recaptcha.verify():
            # Check for errors in the form submitted
            if (request.form["tosAgree"] == "agreed"
                    and request.form["email"] != ""  # not blank email
                    and request.form["name"] != ""  # not blank restaurant name
                    and request.form["password"] != ""  # not blank pw
                    and request.form["password"] == request.form["passwordAgain"]
                    and 4 <= len(request.form["password"]) <= 20):
                try:
                    account = Admin(request.form["name"], request.form["email"],
                                    request.form["password"])

                except EmailAlreadyExistsException as e:
                    flash("Account with email already exists")
                    return redirect(url_for("admin_register"))

                except Exception as e:
                    logging.info("admin_register: error %s" % e)
                    traceback.print_exc()
                    return reg_error(e)  # handle errors here
            else:
                return reg_error()

            # Successfully authenticated
            with shelve.open("accounts", 'c') as db:
                accounts = db["accounts"]
                # For Flask-login
                accounts[account.account_id].authenticated = True
                db["accounts"] = accounts
                login_user(account)

            flash("Your OTP secret is %s. Enter this into your OTP app!"
                  % account.totp_secret)
            return redirect(url_for("admin_myrestaurant"))
        else:
            flash("Please fill out the captcha")

    return render_template("admin/register.html")


@app.route("/admin/logout")
@login_required
@admin_side
def admin_logout():
    return redirect(url_for("logout"))


# API for updating account, to be called by Account Settings
@app.route("/admin/updateAccount", methods=["GET", "POST"])
@login_required
@admin_side
def admin_update_account():
    # TODO: Implement admin account soft-deletion

    if request.method == "GET":
        flash("fail")
        return redirect(url_for("admin_home"))

    # Check if current password entered was correct
    if not current_user.check_password_hash(request.form["updateSettingsPw"]):
        flash("Current Password is Wrong")
        return redirect(url_for("admin_home"))

    if "changeName" in request.form:
        if request.form["changeName"] != "":
            current_user.set_name(request.form["changeName"])
            flash("Successfully updated name to %s" % request.form[
                "changeName"])

    if "changeEmail" in request.form:
        if request.form["changeEmail"] != "":
            result = (current_user.set_email(request.form["changeEmail"]))
            if result == Account.EMAIL_CHANGE_SUCCESS:
                flash("Successfully updated email")
            elif result == Account.EMAIL_CHANGE_ALREADY_EXISTS:
                flash("Failed updating email, Email already Exists")
            elif result == Account.EMAIL_CHANGE_INVALID:
                flash("Failed updating email, email is Invalid")

    if "changePw" in request.form:
        if request.form["changePw"] != request.form["changePwConfirm"]:
            flash("Confirm Password does not match Password")
        elif request.form["changePw"] != "":
            current_user.set_password_hash(request.form["changePw"])
            flash("Successfully updated password")

    return redirect(url_for("admin_home"))


# Can be used for all account types
@app.route("/deleteAccount", methods=["POST"])
@login_required
def delete_account():
    if current_user.is_authenticated and "updateSettingsPw" in request.form:
        if current_user.check_password_hash(request.form["updateSettingsPw"]):
            with shelve.open(ACCOUNT_DB, 'c') as db:
                accounts = db["accounts"]
                account = accounts.get(current_user.account_id)
                account.disabled = True
                db["accounts"] = accounts

            flash("Successfully deleted your account")
            return redirect(url_for("logout"))
        else:
            flash("Incorrect password")
    else:
        flash("Failed to delete your account!")

    if isinstance(current_user, Admin):
        return redirect(url_for("admin_home"))
    else:
        return redirect(url_for("consumer_home"))


@app.route("/admin/coupon")
@login_required
@admin_side
def admin_coupon_management():
    # Get current CouponSystem from current_user (admin).
    coupon_system_id = current_user.coupon_system_id
    coupon_system = CouponSystem.query(coupon_system_id)
    coupon_list = coupon_system.get_coupons()
    count = len(coupon_list)

    return render_template("admin/retrieveCoupons.html",
                           coupon_list=coupon_list,
                           count=count)


@app.route("/admin/addCoupon", methods=["GET", "POST"])
@login_required
@admin_side
def admin_coupon_add():
    create_coupon_form = CreateCouponForm(request.form)

    if request.method == "POST" and create_coupon_form.validate():
        if create_coupon_form.expiry.data < date.today():
            flash("Date entered cannot be in the past!")
            return redirect(url_for("admin_coupon_add"))

        cs = CouponSystem.query(current_user.coupon_system_id)

        if create_coupon_form.discount_type.data == "fp":
            discount_type = CouponSystem.DISCOUNT_FIXED_PRICE
            discount_amount = float(create_coupon_form.discount_amount.data),
            discount_amount = discount_amount[
                0]  # for some reason we get a tuple here

            if discount_amount < 0:
                flash("Discount pricing can't be negative")
                return redirect(url_for("admin_coupon_add"))

        elif create_coupon_form.discount_type.data == "pct":
            discount_type = CouponSystem.DISCOUNT_PERCENTAGE_OFF
            discount_amount = float(
                create_coupon_form.discount_amount.data) / 100

            if discount_amount > 1:
                flash("Discount percentage can't be greater than 100%.")
                return redirect(url_for("admin_coupon_add"))

            if discount_amount < 0.01:
                flash("Discount percentage can't be less than 1%.")
                return redirect(url_for("admin_coupon_add"))
        else:
            flash("Invalid discount type!")
            return redirect(url_for("admin_coupon_add"))

        food_item_ids = create_coupon_form.food_item_ids.data.split()
        # Convert all item IDs entered to integers
        food_item_ids = [int(i) for i in food_item_ids]

        # TODO: Check if food item ids belong to the current restaurant.

        cs.new_coupon(create_coupon_form.coupon_code.data,
                      food_item_ids,
                      discount_type,
                      discount_amount,
                      create_coupon_form.expiry.data)

        return redirect(url_for("admin_coupon_management"))
    else:
        return render_template("admin/createCoupon.html",
                               form=create_coupon_form)


@app.route("/admin/updateCoupon/<string:coupon_code>", methods=["GET", "POST"])
@login_required
@admin_side
def admin_coupon_update(coupon_code):
    cs = CouponSystem.query(current_user.coupon_system_id)
    coupon = cs.get_coupon(coupon_code)

    if not coupon:
        flash("Can't edit non-existent coupon with code %s" % coupon_code)
        return redirect(url_for("admin_coupon_management"))

    update_coupon_form = CreateCouponForm(request.form)

    if request.method == "POST" and update_coupon_form.validate():
        if update_coupon_form.expiry.data < date.today():
            flash("Date entered cannot be in the past!")
            return redirect(url_for("admin_coupon_management"))

        if update_coupon_form.discount_type.data == "fp":
            discount_type = CouponSystem.DISCOUNT_FIXED_PRICE
            discount_amount = float(update_coupon_form.discount_amount.data),
            # for some reason we get a tuple here
            discount_amount = discount_amount[0]
        elif update_coupon_form.discount_type.data == "pct":
            discount_type = CouponSystem.DISCOUNT_PERCENTAGE_OFF
            discount_amount = float(
                update_coupon_form.discount_amount.data) / 100
        else:
            flash("Invalid discount type!")
            return redirect(url_for("admin_coupon_add"))

        food_item_ids = update_coupon_form.food_item_ids.data.split()
        food_item_ids = [int(i) for i in food_item_ids]

        # TODO: Check if food item ids belong to the current restaurant.

        cs.edit_coupon(coupon_code,
                       update_coupon_form.coupon_code.data,
                       food_item_ids,
                       discount_type,
                       discount_amount,
                       update_coupon_form.expiry.data)

        return redirect(url_for("admin_coupon_management"))

    discount_type = ""
    discount_amount = 0.0
    if coupon.discount.discount_type == CouponSystem.DISCOUNT_FIXED_PRICE:
        discount_type = "fp"
        discount_amount = coupon.discount.discount_amount
    elif coupon.discount.discount_type == CouponSystem.DISCOUNT_PERCENTAGE_OFF:
        discount_type = "pct"
        discount_amount = coupon.discount.discount_amount * 100

    food_items_str = ' '.join(str(i) for i in coupon.food_items)

    update_coupon_form.coupon_code.data = coupon.coupon_code
    update_coupon_form.food_item_ids.data = food_items_str
    update_coupon_form.discount_type.data = discount_type
    update_coupon_form.discount_amount.data = discount_amount
    update_coupon_form.expiry.data = coupon.expiry
    return render_template("admin/updateCoupon.html", form=update_coupon_form,
                           coupon_code=coupon_code)


@app.route("/admin/deleteCoupon/<string:coupon_code>", methods=["GET", "POST"])
@login_required
@admin_side
def admin_coupon_delete(coupon_code):
    cs = CouponSystem.query(current_user.coupon_system_id)
    cs.delete_coupon(coupon_code)

    return redirect(url_for("admin_coupon_management"))


@app.route("/admin/testCoupon", methods=["POST"])
@login_required
@admin_side
def coupon_tester():
    cs = CouponSystem.query(current_user.coupon_system_id)
    food_id = int(request.form["foodID"])
    discount_code = request.form["discountCode"]

    try:
        dp = cs.discounted_price(food_id, discount_code)
    except FoodIdNotExistsError:
        flash("Food ID doesn't exist. You need to create it first.")
    else:
        flash("Discounted price is $%.2f" % dp)

    return redirect(url_for("admin_coupon_management"))


@app.route("/admin/reviews")
@login_required
@admin_side
def admin_retrieve_reviews():
    list_of_reviews = ReviewDao.get_reviews(current_user.restaurant_id)
    average_rating = ReviewDao.get_average_rating(current_user.restaurant_id)
    return render_template("admin/retrieveReviews.html",
                           list_of_reviews=list_of_reviews,
                           count=len(list_of_reviews),
                           average_rating=average_rating,
                           threshold=Review.TRUSTWORTHINESS_THRESHOLD)


@app.route("/admin/forgetPassword", methods=["GET", "POST"])
@admin_side
def admin_forget_password():
    if request.method == "POST":
        try:
            email = request.form["email"]
            account = Account.get_account_by_email(email)
            if account is not None:
                flash("An email with a link has been sent.")
                account.reset_password()
                return redirect(url_for("admin_forget_password_key"))
            else:
                flash("Email doesn't exist.")
        except AssertionError:
            flash("FoodyPulse's SMTP email and password wasn't properly "
                  "configured. "
                  "Please contact FoodyPulse support.")

    return render_template("admin/account/forgetPassword.html")


@app.route("/admin/forgetPasswordKey", methods=["GET", "POST"])
@admin_side
def admin_forget_password_key():
    if request.method == "POST":
        email = request.form["email"]
        account = Account.get_account_by_email(email)
        tok = request.form["token"]
        if account is not None:
            return redirect(url_for("password_auto_reset",
                                    account_id=account.account_id,
                                    pw_reset_token=tok))
        else:
            flash("Invalid email")
    return render_template("admin/account/forgetPasswordKey.html")


@app.route("/admin/deleteReview/<int:review_id>")
@admin_side
@login_required
def admin_delete_review(review_id):
    review = ReviewDao.query(review_id)
    if review.delete_untrustworthy():
        flash("Successfully deleted review")
    else:
        flash("Can't delete review as it is above the trust threshold")
    return redirect(url_for("admin_retrieve_reviews"))