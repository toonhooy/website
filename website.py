#!/usr/bin/env python
import sys
import os
import pandas as pd
import config
from flask import Flask, render_template, send_file, flash, redirect, url_for, safe_join, request, abort
from forms import SearchForm, DownloadForm, EmptyForm
import plot

if sys.version_info.major >= 3:
    from io import StringIO
else:
    from StringIO import StringIO

c = config.Config()

try:
    from opengrid.library import houseprint
except ImportError:
    sys.path.append(c.get('backend', 'opengrid'))
    from opengrid.library import houseprint

app = Flask(__name__)
SECRET_KEY = "secret_key"  # TODO add a real key in the config file
app.config.from_object(__name__)

try:
    hp = houseprint.Houseprint()
except:
    print("Connection failed, loading houseprint from cache")
    hp = houseprint.load_houseprint_from_file("cache_hp.hp")
else:
    hp.save("cache_hp.hp")


@app.route("/")
@app.route("/index")
def index():
    return render_template('index.html')


@app.route("/data")
def data():
    devices = hp.get_devices()
    devices.sort(key=lambda x: x.key)
    return render_template('data.html', fluksos=devices)


@app.route("/development")
def development():
    return render_template('development.html')


@app.route("/subscribe")
def subscribe():
    return render_template('subscribe.html')


@app.route("/flukso/<fluksoid>")
def flukso(fluksoid):
    f = hp.find_device(fluksoid)

    if f is None:
        abort(404)

    sensors = f.get_sensors()
    sensors.sort(key=lambda x: x.type)

    return render_template(
            'flukso.html',
            flukso=f,
            sensors=sensors
    )


@app.route("/sensor/<sensorid>")
def sensor(sensorid):
    s = hp.find_sensor(sensorid)

    if s is None:
        abort(404)

    path = c.get('backend', 'figures')

    analyses = []

    # create timeseries plot
    filename = 'TimeSeries_{}.html'.format(s.key)
    analyses.append(
            plot.Html(
                    title='Timeseries',
                    content=safe_join(path, filename),
                    description='Uitleg' # TODO Change description
            )
    )

    if s.type == 'electricity' and not s.system == 'solar':
        # create standby horizontal
        filename = 'standby_horizontal_{}.png'.format(s.key)
        analyses.append(
            plot.Figure(
                title='Standby Horizontal',
                content=filename,
                description='Uitleg' # TODO Change description
            )
        )
        # create standby vertical
        filename = 'standby_vertical_{}.png'.format(s.key)
        analyses.append(
            plot.Figure(
                title='Standby Vertical',
                content=filename,
                description='Uitleg' # TODO Change description
            )
        )

    analyses = [analysis for analysis in analyses if analysis.has_content()]

    return render_template(
        'sensor.html',
        sensor=s,
        analyses=analyses
    )


@app.route("/figures/<filename>")
def figure(filename):
    path = c.get('backend', 'figures')
    file_path = safe_join(path, filename)

    return send_file(file_path)


def figure_exists(filename):
    path = c.get('backend', 'figures')
    file_path = safe_join(path, filename)

    return os.path.exists(file_path)


@app.route("/search", methods=['GET', 'POST'])
def search():
    form = SearchForm()
    if request.method == 'POST' and form.validate():
        f = hp.find_device(form.search_string.data)
        if f is not None:  # flukso was found
            return redirect(url_for('flukso', fluksoid=f.key))
        else:
            flash("Sorry, we couldn't find that Fluksometer")

    return render_template(
            "search.html",
            form=form)


@app.route("/download", methods=['GET', 'POST'])
@app.route("/download/<guid>")
def download(guid=None):
    form = DownloadForm()

    if request.method == 'POST' and form.validate():
        s = hp.find_device(form.guid.data)
        if s is None:
            s = hp.find_sensor(form.guid.data)

        if s is None:
            flash("ID not found")
        else:
            try:
                # We need to connect and disconnect with tmpo
                # to make sure the website doesn't lock access to the sqlite
                hp.init_tmpo()
                tmpos = hp.get_tmpos()
                output = StringIO()
                df = s.get_data(
                        head=pd.Timestamp(form.start.data),
                        tail=pd.Timestamp(form.end.data),
                        resample=form.resample.data
                )
                tmpos.dbcon.close()
            except:
                # This will happen if another process is currently using the tmpo
                flash("Error connecting to the data storage, please try again later")
            else:
                df.to_csv(output, encoding='utf-8')
                output.seek(0)
                return send_file(
                        output,
                        mimetype="text/csv",
                        as_attachment=True,
                        attachment_filename='{}.csv'.format(s.key)
                )
    if guid is not None:
        form.guid.data = guid

    return render_template(
            'download.html',
            form=form
    )


@app.route("/issue30", methods=['GET', 'POST'])
def issue30():
    form = EmptyForm() # Empty form, only validates the secret token to protect against cross-site scripting

    if request.method == 'POST' and form.validate():
        try:
            hp.init_tmpo()
            tmpos = hp.get_tmpos()
            hp.sync_tmpos()
            tmpos.dbcon.close()
        except:
            flash("Error syncing TMPO, please try again later")
        else:
            flash("TMPO Sync Successful")

    return render_template(
        'issue30.html',
        form=form
    )


@app.errorhandler(404)
def internal_error(error):
    flash('ERROR 404 - Page not found')
    return redirect(url_for('index'))


if __name__ == "__main__":
    try:
        env = c.get('env', 'type')
    except:
        env = 'prod'

    if env == 'dev':
        app.run(debug=True)
    else:
        app.run(debug=False, host='0.0.0.0', port=5000)
