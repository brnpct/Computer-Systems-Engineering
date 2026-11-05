from flask import Flask, render_template, jsonify, request, send_from_directory
from multiprocessing import Process, Event
import server_core, os, json
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import time

app = Flask(__name__)
os.makedirs("plots", exist_ok=True)

@app.route("/plots/<path:filename>")
def serve_plots(filename):
    return send_from_directory("plots", filename)

proc = None
stop_event = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/topics/view")
def topic_view():
    return render_template("topics.html")

@app.route("/stats/view")
def stats_view():
    return render_template("stats.html")

@app.route("/users/view")
def users_view():
    return render_template("users.html")

@app.route("/server/stop", methods=["POST"])
def stop():
    global proc, stop_event
    if proc:
        stop_event.set()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.terminate()
            proc.join()
        proc = None
    return jsonify({"running": False})

@app.route("/server/reboot", methods=["POST"])
def reboot():
    global proc, stop_event
    if proc:
        stop_event.set()
        proc.join()
    stop_event = Event()
    proc = Process(target=server_core.run_server, args=(stop_event, "reboot"))
    proc.start()
    return jsonify({"running": True})

@app.route("/server/fresh", methods=["POST"])
def fresh():
    global proc, stop_event
    if proc:
        stop_event.set()
        proc.join()
    stop_event = Event()
    proc = Process(target=server_core.run_server, args=(stop_event, "fresh"))
    proc.start()
    return jsonify({"running": True})


# this isnt being used since we didn't end up implementing it in a reasonable way
@app.route("/topics", methods=["POST"])
def add_topic_route():
    topic = request.json.get("topic")
    if not topic:
        return jsonify({"result": "Failure", "error": "missing topic"}), 400
    
    os.makedirs("topics", exist_ok=True)
    path = f"topics/{topic}.log"
    
    if os.path.exists(path):
        return jsonify({"result": "Failure", "error": "topic exists"})
    
    open(path, "a").close()
    
    global proc, stop_event
    if proc:
        stop_event.set()
        proc.join()
    
    stop_event = Event()
    proc = Process(target=server_core.run_server, args=(stop_event, "reboot"))
    proc.start()
    
    return jsonify({"result": "Success"})

@app.route("/topics/list")
def list_topics():
    if not os.path.exists("topics"):
        return jsonify([])
    return jsonify([f.removesuffix(".log") for f in os.listdir("topics")])

@app.route("/topics/posts/<topic>")
def topic_posts(topic):
    path = f"topics/{topic}.log"
    if not os.path.exists(path):
        return jsonify([])

    posts = {}
    with open(path) as f:
        for line in f:
            if line.strip():
                e = json.loads(line)
                if e["event"] == "post":
                    i = int(list(e["post"].keys())[0])
                    posts.update({int(k): v for k, v in e["post"].items()})
    return jsonify(posts)

@app.route("/users")
def users():
    user_database = {}
    with open("users.log") as f:
        for line in f:
            e = json.loads(line)
            if e["event"] == "register":
                user_database[e["user"]] = {
                    "password": e["password"],
                    "topics": {},
                    "metadata": {}
                }
            elif e["event"] == "subscribe":
                user_database[e["user"]]["topics"][e["topic"]] = 0
            elif e["event"] == "view":
                user = e["user"]
                topic = e["topic"]
                post_id = e["post_id"]
                if user in user_database and topic in user_database[user]["topics"]:
                    user_database[user]["topics"][topic] = max(
                        user_database[user]["topics"][topic],
                        post_id
                    )
    
    for user in user_database:
        user_database[user]["topics_list"] = list(user_database[user]["topics"].keys())
    
    return jsonify(user_database)

@app.route("/server/status")
def server_status():
    return jsonify({
        "running": proc is not None and proc.is_alive()
    })

@app.route("/stats/latest")
def stats_latest():
    if not os.path.exists("stats.log"):
        return jsonify({})
    
    with open("stats.log") as f:
        lines = [l for l in f if l.strip()]
        if not lines:
            return jsonify({})
        return jsonify(json.loads(lines[-1]))

@app.route("/stats/history")
def stats_history():
    if not os.path.exists("stats.log"):
        return jsonify([])
    
    with open("stats.log") as f:
        return jsonify([json.loads(l) for l in f if l.strip()])

def generate_plot(metric, filename):
    if not os.path.exists("stats.log"):
        return False

    times, values = [], []
    with open("stats.log") as f:
        for line in f:
            if line.strip():
                s = json.loads(line)
                times.append(s["time"])
                if metric == "latency":
                    values.append(s["avg_latency_ms"])
                elif metric == "cpu":
                    values.append(s["cpu_percent"])
                elif metric == "mem":
                    values.append(s["memory"]["percent"])
                elif metric == "disk":
                    values.append(s["disk"]["percent"])

    if not times:
        return False

    plt.figure(figsize=(6,2))
    plt.plot(values[-200:], marker='o', linewidth=2, color='#1f77b4', markersize=2)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.xticks([])
    
    if metric == "latency":
        plt.ylim(bottom=0)
    else:
        plt.ylim(0, 100)

    plt.title(metric.capitalize())
    plt.tight_layout()
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    plt.savefig(filename)
    plt.close()
    return True

@app.route("/stats/update_plots")
def update_plots():
    generate_plot("latency", "plots/latency.png")
    generate_plot("cpu", "plots/cpu.png")
    generate_plot("mem", "plots/mem.png")
    generate_plot("disk", "plots/disk.png")
    return "ok"

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)