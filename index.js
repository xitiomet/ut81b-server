function getXmlHttp()
{
    var xmlhttp;
    if (window.XMLHttpRequest) {
        xmlhttp = new XMLHttpRequest();
    } else if (window.ActiveXObject) {
        xmlhttp = new ActiveXObject("Microsoft.XMLHTTP");
    } else {
        alert("Your browser does not support XMLHTTP!");
    }
    return xmlhttp;
}

function popout()
{
    var myWindow = window.open(window.location, "Multimeter", "width=340,height=480");
}

function horizDash(ctx, y)
{
    ctx.beginPath();
    ctx.setLineDash([4, 2]);
    ctx.moveTo(0, 120 - y);
    ctx.lineTo(320, 120 - y);
    ctx.stroke();
    ctx.setLineDash([]);
}

function horizDot(ctx, y)
{
    ctx.beginPath();
    ctx.setLineDash([2, 4]);
    ctx.moveTo(0, 120 - y);
    ctx.lineTo(320, 120 - y);
    ctx.stroke();
    ctx.setLineDash([]);
}

function plotData(range, plot)
{
    var c = document.getElementById("graph");
    var ctx = c.getContext("2d");
    ctx.clearRect(0, 0, 320, 240);
    for(i = -8; i < 8; i++)
    {
        if (i == 0)
        {
            horizDash(ctx, i * (240/8))
        } else {
            horizDot(ctx, i * (240/8))
        }
    }
    ctx.beginPath();
    ctx.moveTo(0, 120);
    if (plot.y.length == 320)
    {
        for(point = 0; point < 320; point++)
        {
            ctx.lineTo(point, 120 - ((plot.y[point]/(range + 2.5)) * 60));
            ctx.stroke();
        }
        c.style.display = 'block';
    } else {
        c.style.display = 'none';
    }
    
}

function handleResponse(response)
{
    var out = "<table style=\"font-size: 26px; width: 320px;\" cellpadding=\"2\" cellspacing=\"0\">";
    out += "<tr><td style=\"background-color: white; font-size: 36px; text-align: center;\" colspan=\"2\">" + response.mode + "</td></tr>";
    var reading_color = "black";
    if (response.reading.value1 > 0.0)
    {
        reading_color = "green";
    } else if (response.reading.value1 < 0.0) {
        reading_color = "red";
    }
    if (response.mode != "Off")
    {
        out += "<tr><td style=\"color: " + reading_color + "; background-color: white; text-align: left; font-size: 48px;\">" + response.reading.value1 + " " + response.reading.scale1 + "</td><td style=\"padding-left: 14px; text-align: right;\">" + response.reading.value2 + " " + response.reading.scale2 + "</td></tr>";
        out += "<tr><td style=\"background-color: white;\">Range " + response.range + "</td><td style=\"padding-left: 14px; text-align: right;\">" + response.current + "</td></tr>";
    }
    out += "</table>";
    document.getElementById('table_display').innerHTML = out;
    plotData(response.range, response.plot);
}

function dataRefresh()
{
    var refresh_timeout = 10000;
    xmlhttp = getXmlHttp();
    xmlhttp.onreadystatechange=function()
    {
        if (xmlhttp.readyState == 4)
        {
            var rtext = xmlhttp.responseText;
            if (rtext != '')
            {
                var response = eval('(' + rtext + ')');
                handleResponse(response);
                if (response.mode != "Off")
                {
                    refresh_timeout = 1000;
                } else {
                    refresh_timeout = 10000;
                }
            }
            setTimeout("dataRefresh()", refresh_timeout);
        }
    };
    xmlhttp.open("POST", "api.json?rnd=" + Math.random(10000), true);
    xmlhttp.send(null);
}
