"""
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from client_lib import SecureClient
import uuid
import threading
import sys 

port = sys.argv[1]
SERVER_HOST = sys.argv[2]

app = Flask(__name__)
app.secret_key = "dev-secret"  # change for production


clients = {}  # session_id -> SecureClient
client_lock = threading.Lock()

def get_client():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    sid = session["sid"]
    if sid not in clients:
        clients[sid] = SecureClient(SERVER_HOST)
    return clients[sid]


def get_profile():
    username = session.get("username")
    if username:
        client = get_client()
        with client_lock:
            res = client.request({"c": "profile", "u": username})
        # Convert topics list back to dict if needed
        profile = res.get("result", {"topics": []})
        # If it's a list, convert to dict for internal use
        if isinstance(profile.get("topics"), list):
            profile["topics_dict"] = {topic: 0 for topic in profile["topics"]}
        return profile
    else:
        return {"topics": [], "topics_dict": {}}

@app.route("/profile_ajax")
def profile_ajax():
    username = request.args.get("username", "")
    client = get_client()
    try:
        with client_lock:
            res = client.request({"c": "profile", "u": username})
        profile = res.get("result", {"topics": []})
    except:
        profile = {"topics": []}
    return jsonify(profile)


def get_topics(subscribed_topics=None):
    client = get_client()
    with client_lock:
        topics = client.request({"c": "listtopics"})["result"]
    
    if subscribed_topics is None:
        username = session.get("username")
        if username:
            profile = get_profile()
            # Handle both list and dict formats
            if isinstance(profile.get("topics"), dict):
                subscribed_topics = list(profile["topics"].keys())
            else:
                subscribed_topics = profile.get("topics", [])
        else:
            subscribed_topics = []
    
    topics_for_template = []
    for t in topics:
        topic_name = t[0]
        topics_for_template.append({
            "topic": topic_name,
            "posts": t[1],
            "subscribers": t[2],
            "active": t[3],
            "subscribed": topic_name in subscribed_topics
        })
    return topics_for_template

@app.route("/topics_status")
def topics_status():
    username = session.get("username")
    if username:
        profile = get_profile()
        subscribed_topics = profile["topics"]
    else:
        subscribed_topics = []

    topics_data = get_topics(subscribed_topics=subscribed_topics)
    return jsonify(topics_data)

@app.route("/", methods=["GET", "POST"])
def login():
    client = get_client()
    topics = get_topics()
    if request.method == "POST":
        # Login
        username = request.form["username"]
        password = request.form["password"]
        topic = request.form.get("topic", "")
        with client_lock:
            res = client.request({"c": "login", "u": username, "p": password, "t": topic})
        if res["result"] != "Failure":
            session["username"] = request.form["username"] 
            session["ut"] = res["result"]
            session["topic"] = request.form["topic"]
            return redirect(url_for("feed"))

        else:
            return render_template("login.html", topics=topics, error="Invalid login")
    return render_template("login.html", topics=topics)

@app.route("/register", methods=["GET", "POST"])
def register():
    client = get_client()
    topics = get_topics()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        selected_topics = request.form.getlist("topics")
        with client_lock:
            res = client.request({"c": "register", "u": username, "p": password})
        if res["result"] == "Success":
            # Subscribe to selected topics
            for t in selected_topics:
                with client_lock:
                    client.request({"c": "subscribe", "u": username, "p": password, "t": t})
            return redirect(url_for("login"))
        else:
            return render_template("register.html", topics=topics, error="Username taken")
    return render_template("register.html", topics=topics)

@app.route("/subscribe_direct", methods=["POST"])
def subscribe_direct():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    topic = data.get("topic")

    client = get_client()

    with client_lock:
        sub_res = client.request({"c": "subscribe", "u": username, 'p': password, "t": topic})

    if sub_res["result"] == "Failure":
        return {"result": "Invalid username/password"}, 400

    return {"result": sub_res["result"]}


@app.route("/feed")
def feed():
    if "ut" not in session:
        return redirect(url_for("login"))

    # Mark first refresh as True on login
    session["first_refresh"] = True

    topics = get_topics()
    return render_template("feed.html", topics=topics, current_topic=session.get("topic", ""), username=session["username"])

@app.route("/publish", methods=["POST"])
def publish_post():
    client = get_client()
    text = request.form["post"]
    reply_to = request.form.get("reply_to")  # might be None
    with client_lock:
        res = client.request({
            "c": "publish",
            "ut": session["ut"],
            "t": session["topic"],
            "post": text,
            "r": int(reply_to) if reply_to else None
        })
    return "", 204

@app.route("/refresh")
def ajax_refresh():

    if "ut" not in session or "sid" not in session:
        return jsonify({"posts": []})

    sid = session["sid"]
    if sid not in clients:
        return jsonify({"posts": []})

    client = clients[sid]
    
    # Determine if this is the first refresh
    first_refresh = session.pop("first_refresh", True)  # True on login or topic switch
    old_flag = first_refresh  # True on first refresh, False thereafter
    session["first_refresh"] = False  # mark that we've done the first refresh
    
    with client_lock:
        res = client.request({
            "c": "refresh",
            "ut": session["ut"],
            "t": session["topic"],
            "old": old_flag  
        })
    posts = res.get("posts", [])
    return jsonify({"posts": posts})


@app.route("/change_topic", methods=["POST"])
def change_topic():
    sid = session["sid"]
    if sid in clients:
        try:
            clients[sid].close()
        except Exception:
            pass        
        del clients[sid]

    client = get_client()
    new_topic = request.form["topic"]
    profile = get_profile()
    if new_topic not in profile["topics"]:
        return "Not subscribed", 400
    session["topic"] = new_topic
    session["first_refresh"] = True

    return redirect(url_for("feed"))

@app.route("/change_topic_reauth", methods=["POST"])
def change_topic_reauth():
    data = request.get_json()
    topic = data["topic"]
    password = data["password"]
    username = session["username"]

    # Kill old client cleanly
    sid = session.get("sid")
    if sid in clients:
        try:
            clients[sid].close()
        except:
            pass
        del clients[sid]

    # Create fresh client
    new_sid = str(uuid.uuid4())
    client = SecureClient(SERVER_HOST)

    # Login again
    with client_lock:
        res = client.request({
            "c": "login",
            "u": username,
            "p": password,
            "t": topic
        })

    if res["result"] == "Failure":
        client.close()
        return jsonify({"result": "Failure"})

    # Save session state
    session["sid"] = new_sid
    session["ut"] = res["result"]
    session["topic"] = topic
    session["first_refresh"] = True

    clients[new_sid] = client

    return jsonify({"result": "Success"})

@app.route("/server_stats")
def server_stats():
    client = get_client()
    with client_lock:
        res = client.request({"c": "stats"})
    # res["result"] = [user_count, topic_count, post_count, avg_latency_ms, operations]
    return jsonify({
        "latency": res["result"][3],  # avg operation latency in ms
        "operations": res["result"][4]
    })


@app.route("/logout")
def logout():
    sid = session.get("sid")

    # Close the client connection
    if sid and sid in clients:
        try:
            clients[sid].close()
        except Exception:
            pass
        del clients[sid]

    # Clear the session
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True,port=port)
"""
from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from client_lib import SecureClient
import uuid
import threading
import sys 

port = sys.argv[1]
SERVER_HOST = sys.argv[2]

app = Flask(__name__)
app.secret_key = "dev-secret"

clients = {}
client_lock = threading.Lock()

def get_client():
    if "sid" not in session:
        session["sid"] = str(uuid.uuid4())
    sid = session["sid"]
    if sid not in clients:
        clients[sid] = SecureClient(SERVER_HOST)
    return clients[sid]

def get_profile():
    username = session.get("username")
    if username:
        client = get_client()
        with client_lock:
            res = client.request({"c": "profile", "u": username})
        return res.get("result", {"topics": []})
    else:
        return {"topics": []}

@app.route("/profile_ajax")
def profile_ajax():
    username = request.args.get("username", "")
    client = get_client()
    try:
        with client_lock:
            res = client.request({"c": "profile", "u": username})
        profile = res.get("result", {"topics": []})
    except:
        profile = {"topics": []}
    return jsonify(profile)

def get_topics(subscribed_topics=None):
    topics = []
    try:
        client = get_client()
        with client_lock:
            topics_result = client.request({"c": "listtopics"})["result"]
        
        if subscribed_topics is None:
            username = session.get("username")
            if username:
                profile = get_profile()
                subscribed_topics = profile.get("topics", [])
            else:
                subscribed_topics = []
        
        for t in topics_result:
            topic_name = t[0]
            topics.append({
                "topic": topic_name,
                "posts": t[1],
                "subscribed": topic_name in subscribed_topics
            })
    except:
        pass
    
    return topics

@app.route("/topics_status")
def topics_status():
    username = session.get("username")
    if username:
        profile = get_profile()
        subscribed_topics = profile.get("topics", [])
    else:
        subscribed_topics = []

    topics_data = get_topics(subscribed_topics=subscribed_topics)
    return jsonify(topics_data)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        topic = request.form.get("topic", "")
        
        # Create a fresh client for the login attempt
        client = SecureClient(SERVER_HOST)
        try:
            res = client.request({"c": "login", "u": username, "p": password})
            
            if res["result"] != "Failure":
                # Login successful - set up session
                session["username"] = username
                session["ut"] = res["result"]
                session["topic"] = topic
                
                # Close the temporary client
                client.close()
                
                # Now create the proper session client
                get_client()  # This will create a fresh client for the session
                
                return redirect(url_for("feed"))
            else:
                client.close()
                return render_template("login.html", topics=[], error="Invalid login")
        except Exception as e:
            client.close()
            return render_template("login.html", topics=[], error="Connection error")
    
    # GET request - just show topics without creating a client
    topics = []
    try:
        # Create a temporary client just to get topics
        temp_client = SecureClient(SERVER_HOST)
        with client_lock:
            topics_result = temp_client.request({"c": "listtopics"})["result"]
        temp_client.close()
        
        # Format topics for template
        for t in topics_result:
            topics.append({
                "topic": t[0],
                "posts": t[1],
                "subscribed": False  # We don't know yet for GET
            })
    except:
        pass  # If we can't get topics, show empty list
    
    return render_template("login.html", topics=topics)

@app.route("/register", methods=["GET", "POST"])
def register():
    client = get_client()
    topics = get_topics()
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        selected_topics = request.form.getlist("topics")
        
        with client_lock:
            res = client.request({"c": "register", "u": username, "p": password})
        
        if res["result"] == "Success":
            # Subscribe to selected topics
            for t in selected_topics:
                with client_lock:
                    client.request({"c": "subscribe", "u": username, 'p': password, "t": t})
            return redirect(url_for("login"))
        else:
            return render_template("register.html", topics=topics, error="Username taken")
    return render_template("register.html", topics=topics)

@app.route("/subscribe_direct", methods=["POST"])
def subscribe_direct():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")
    topic = data.get("topic")

    client = get_client()
    with client_lock:
        sub_res = client.request({"c": "subscribe", "u": username, 'p': password, "t": topic})
    
    if sub_res["result"] == "Failure":
        return {"result": "Invalid username/password"}, 400
    return {"result": sub_res["result"]}

@app.route("/feed")
def feed():
    if "ut" not in session:
        return redirect(url_for("login"))
    
    session["first_refresh"] = True
    topics = get_topics()
    return render_template("feed.html", 
                         topics=topics, 
                         current_topic=session.get("topic", ""), 
                         username=session["username"])

@app.route("/publish", methods=["POST"])
def publish_post():
    client = get_client()
    text = request.form["post"]
    reply_to = request.form.get("reply_to")
    
    with client_lock:
        res = client.request({
            "c": "publish",
            "ut": session["ut"],
            "t": session["topic"],
            "post": text,
            "r": int(reply_to) if reply_to else None
        })
    return "", 204

@app.route("/refresh")
def ajax_refresh():
    if "ut" not in session or "sid" not in session:
        return jsonify({"posts": []})
    
    sid = session["sid"]
    if sid not in clients:
        return jsonify({"posts": []})
    
    client = clients[sid]
    first_refresh = session.pop("first_refresh", True)
    old_flag = first_refresh
    session["first_refresh"] = False
    
    with client_lock:
        res = client.request({
            "c": "refresh",
            "ut": session["ut"],
            "t": session["topic"],
            "old": old_flag
        })
    
    posts = res.get("posts", [])
    return jsonify({"posts": posts})

@app.route("/change_topic", methods=["POST"])
def change_topic():
    sid = session["sid"]
    if sid in clients:
        try:
            clients[sid].close()
        except Exception:
            pass        
        del clients[sid]

    client = get_client()
    new_topic = request.form["topic"]
    profile = get_profile()
    if new_topic not in profile.get("topics", []):
        return "Not subscribed", 400
    
    session["topic"] = new_topic
    session["first_refresh"] = True
    return redirect(url_for("feed"))

@app.route("/change_topic_reauth", methods=["POST"])
def change_topic_reauth():
    data = request.get_json()
    topic = data["topic"]
    password = data["password"]
    username = session["username"]

    sid = session.get("sid")
    if sid in clients:
        try:
            clients[sid].close()
        except:
            pass
        del clients[sid]

    new_sid = str(uuid.uuid4())
    client = SecureClient(SERVER_HOST)

    with client_lock:
        res = client.request({
            "c": "login",
            "u": username,
            "p": password
        })

    if res["result"] == "Failure":
        client.close()
        return jsonify({"result": "Failure"})

    session["sid"] = new_sid
    session["ut"] = res["result"]
    session["topic"] = topic
    session["first_refresh"] = True
    clients[new_sid] = client

    return jsonify({"result": "Success"})

@app.route("/server_stats")
def server_stats():
    client = get_client()
    with client_lock:
        res = client.request({"c": "stats"})
    return jsonify({
        "latency": res["result"][3],
        "operations": res["result"][4]
    })

@app.route("/logout")
def logout():
    sid = session.get("sid")
    if sid and sid in clients:
        try:
            clients[sid].close()
        except Exception:
            pass
        del clients[sid]
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True, port=port)