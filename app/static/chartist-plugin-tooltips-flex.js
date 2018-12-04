(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    // AMD. Register as an anonymous module.
    define(["chartist"], function (Chartist) {
      return (root.returnExportsGlobal = factory(Chartist));
    });
  } else if (typeof exports === 'object') {
    // Node. Does not work with strict CommonJS, but
    // only CommonJS-like enviroments that support module.exports,
    // like Node.
    module.exports = factory(require("chartist"));
  } else {
    root['Chartist.plugins.Tooltips_flex'] = factory(Chartist);
  }
}(this, function (Chartist) {

  /**
   * Chartist.js plugin to display a tooltip when hovering (or clickin) the chart.
   *
   * TODO: use position approach from zoom plugin instead of looping over points
   * TODO: investigate performance issues with zoomed in flat data. Might be solved when switching to position apporach to translate from svg coords to view
   */
  /* global Chartist */
  (function(window, document, Chartist) {
    'use strict';

    var defaultOptions = {
      tooltipOffset: {
        x: 0,
        y: -15
      },
      tooltipClass: 'chartist-tooltip-flex',
      markerClass: 'chartist-tooltip-flex-marker',
      markerY: false,
      /* Function to merge the two found nearest points.
       * Can be one of: nearest, left, right, interpolate
       * Or a function. See comment over merge_functions.
       * Warning: interpolate doesn't properly work with lineSmooth: true. (TODO)
       * */
      mergeFnc: 'nearest',
      /* Function to create/update the tooltip content.
       * function fn(series, tooltip)...
       *  series contains {name: seriesname, value: value choosen by tooltipMergeFnc} for each series in the graph.
       *  If the return value is not null set it as textContent. tooltip can be used to update html.
       *  this is the plguin object which provides:
       *    options           : The option object
       *    merge_functions   : Object containing all build in merge function
       *    unProjectX(value) : Transforms x data value to svg position
       *    unProjectY(value) : Transforms y data value to svg position
       *    project(value)    : Transforms x svg position to x data value 
       */
      displayFnc: default_tooltip_display,
      /* Adds the tooltipHighlightPointClass to each point returned by the merge function if set. */
      highlightPoint: true,
      highlightPointClass: 'ct-tooltip-point-hit',
      /* Format function for x values. Used by the default tooltipMergeFnc */
      formatX: Chartist.noop,
      /* Format function for y values. Used by the default tooltipMergeFnc */
      formatY: Chartist.noop,
      /* Format function for series names. Used by the default tooltipMergeFnc */
      formatName: function(x){ var n=x.name; return n[0].toUpperCase() + n.substr(1) },
      /* Format function to select which x value is shown. Parameter is an array of all x values. Used by the default tooltipMergeFnc */
      mergeXSeriesFnc: function(x_values){ return x_values[0] }
    };


    /*
     * The default display function.
     * If the return value != null use it as textContent (!) for the tooltip.
     * Use the tooltip parameter if you want to write/update HTML.
     */
    function default_tooltip_display(series, tooltip){
      var x_vals = [];
      var text = "";
      for(var i=0; i < series.length; ++i){
        x_vals.push(series[i].value.x);
        text += this.options.formatName(series[i].series.data) + ": " + this.options.formatY(series[i].value.y) + "\n";
      }
      var x_text = this.options.formatX(this.options.mergeXSeriesFnc(x_vals));
      if(x_text)
        text = x_text + "\n" + text;
      return text;
    }


    /*
     * "Borrowed" from https://stackoverflow.com/a/29018745/4830897
     * Binary search in JavaScript.
     * Returns the index of of the element in a sorted array or (-n-1) where n is the insertion point for the new element.
     * Parameters:
     *     ar - A sorted array
     *     el - An element to search for
     *     compare_fn - A comparator function. The function takes two arguments: (a, b) and returns:
     *        a negative number  if a is less than b;
     *        0 if a is equal to b;
     *        a positive number if a is greater than b.
     * The array may contain duplicate elements. If there are more than one equal elements in the array, 
     * the returned value can be the index of any one of the equal elements.
     */
    function binarySearch(ar, el, compare_fn) {
        var m = 0;
        var n = ar.length - 1;
        while (m <= n) {
            var k = (n + m) >> 1;
            var cmp = compare_fn(el, ar[k]);
            if (cmp > 0) {
                m = k + 1;
            } else if(cmp < 0) {
                n = k - 1;
            } else {
                return k;
            }
        }
        return m - 1;
    }



    Chartist.plugins = Chartist.plugins || {};
    Chartist.plugins.Tooltips_flex = function(options) {
      options = Chartist.extend({}, defaultOptions, options);

      var plugin = function tooltips_flex(chart) {
        var tooltip = document.body.querySelector(options.tooltipClass);
        var chart_container = chart.container;
        var svg = null;
        var series = [];
        var created = false;
        var marker = null, marker_y = null;
        var axis_x = null, axis_y = null; 

        options.displayFnc = options.displayFnc.bind(plugin);
        plugin.options = options;

        /* 
         * Merge functions get the two nearest points for a series and should return
         * one point. One of left or right could be null.
         */
        var merge_functions = plugin.merge_functions = {
            left: function(left, right, point){
              if(!left) left = right;
              return left;
            },
            right: function(left, right, point){
              if(!right) right = left;
              return right;
            },
            nearest: function(left, right, point){
              if(!left) return right;
              if(!right) return left;
              point = project(point);
              if(Math.abs(left.x - point) < Math.abs(right.x - point))
                return left;
              return right;
            },
            interpolate: function(left, right, point){
              if(!left) return right;
              if(!right) return left;
              point = project(point);
              console.log("Point", point);
              var ns = (right.x - left.x);
              var ls = Math.abs(left.x - point) / ns;
              var rs = Math.abs(right.x - point) / ns;
              return {
                x: point,
                y: right.y * ls + left.y * rs
              }
            },
        }

        var width = 0, height = 0;    
        var tooltipMergeFnc = options.mergeFnc;
        if(typeof tooltipMergeFnc !== "function"){
          tooltipMergeFnc = merge_functions[tooltipMergeFnc];
        }

        if(!tooltip){
          tooltip = document.createElement('div');
          tooltip.className = options.tooltipClass;
          // Fallback CSS so its at least visible without the css file.
          tooltip.style.position = 'absolute';
          tooltip.style.whiteSpace = 'pre';
          tooltip.style.top = '0';
          document.body.append(tooltip);
        }

        function get_nearest_points(elements, point){
          var i = binarySearch(elements.raw_x, point, function(a,b){
            if(a > b) return 1;
            if(a < b) return -1;
            return 0;
          });
          var data = elements.data.data;
          var right = null;
          i = Math.max(0, i);
          var left = data[i];
          if(i+1 < data.length){
            right = data[i+1]
          }
          return [left, right];
        }

        var _tooltip_visible = false;
        var rafQueued = false;
        var last_event = null;
        function update(){
          rafQueued = false;
          if(!_tooltip_visible) _show_tooltip();
          var svg_pos = transformToSVG(last_event.pageX, last_event.pageY);
          var values = [];
          var highlightsToAdd = [];
          for(var i=0; i < series.length; ++i){
            var points = get_nearest_points(series[i], svg_pos.x);
            points = tooltipMergeFnc(points[0], points[1], svg_pos.x);
            values.push({value: points, series: series[i]});
          }

          var ret = options.displayFnc(values, tooltip);
          if(ret){
            tooltip.textContent = ret;          
          }
          height = tooltip.offsetHeight;
          width = tooltip.offsetWidth;
          var offsetX = - width / 2 + options.tooltipOffset.x;
          var offsetY = - height + options.tooltipOffset.y;

          /*
          * Try to do all the dom changing at once to limit relayouts.
          */
          tooltip.style.transform = 'translate(' + (last_event.pageX + offsetX) + 'px, ' + (last_event.pageY + offsetY) + 'px)';
          marker.getNode().setAttribute('transform', 'translate('+svg_pos.x+' 0)');
          if(options.markerY){
            marker_y.getNode().setAttribute('transform', 'translate(0 '+svg_pos.y+')');
          }
          if(options.highlightPoint){
            for(var i=0; i < values.length; ++i){
              var p = values[i].value;
              values[i].series.point.getNode().setAttribute('transform', 'translate('+unProjectX(p.x)+' '+unProjectY(p.y)+')');
            }
          }
        }



        function _show_tooltip(){
          tooltip.classList.add('tooltip-show');
          marker.addClass('tooltip-show');
          if(options.markerY){
            marker_y.addClass('tooltip-show');
          }
          _tooltip_visible = true;
        }
        chart_container.addEventListener('mouseenter', function (event) {
          _show_tooltip();
        });

        chart_container.addEventListener('mouseleave', function (event) {
          tooltip.classList.remove('tooltip-show');
          marker.removeClass('tooltip-show');
          if(options.markerY){
            marker_y.removeClass('tooltip-show');
          }
        });

        chart_container.addEventListener('mousemove', function (event) {
          if(!created) return;
          last_event = event;
          // Not really sure the requstAnimationFrame stuff is helping here.
          // It might on slow devices
          if(rafQueued){
            return;
          }
          rafQueued = true;
          requestAnimationFrame(update);
        });


        if (chart instanceof Chartist.Line) {
          chart.on('created', function(data) {
            //console.log("DATA:", data);
            axis_x = data.axisX;
            axis_y = data.axisY;
            var svgElement = chart.svg.getNode();
            svg = svgElement.tagName === 'svg' ? svgElement : svgElement.ownerSVGElement;

            // TODO: there is prob. a nicer function inside chartist already for this.
            // TODO: investigate and get rid of grid requirement.
            var grid = chart.svg.querySelector('.ct-grids');
            var grid_box = grid.getNode().getBoundingClientRect();
            var cont_box = chart.container.getBoundingClientRect();
            var top_padding = grid_box.top - cont_box.top;
            marker = chart.svg.elem('line', {x1: 0, y1: top_padding, x2: 0, y2: grid_box.height + top_padding, style: options.markerClass}, options.markerClass );
            if(options.markerY){            
              var left_padding = grid_box.left - cont_box.left;
              marker_y = chart.svg.elem('line', {x1: left_padding, y1: 0, x2: grid_box.width + left_padding, y2: 0, style: options.markerClass}, options.markerClass );
            }

            series = [];
            var series_data = chart.data.series;
            for(var i=0; i < series_data.length; ++i){
              var data = [];
              var raw_x_data = [];
              var series_name = series_data[i].className ? "."+series_data[i].className : '[*|series-name="'+series_data[i].name+'"]';
              var elem = chart.svg.querySelector(series_name);
              for(var j=0; j < series_data[i].data.length; ++j){
                raw_x_data.push(unProjectX(series_data[i].data[j].x, axis_x));
              }            
              var d = {data: series_data[i], raw_x: raw_x_data, svg: elem};
              if(options.highlightPoint){
                d.point = elem.elem('line', {x1: 0, y1: 0, x2: 0.01, y2: 0}, chart.options.classNames.point + ' ' + options.highlightPointClass);
              }
              series.push(d);
              console.log("series:", d);
            }
            created = true;
          });
        }

        /*
         * Transforms screen coordinates into svg coordinates 
         */
        var _point = null;
        function transformToSVG(x, y) {
          var matrix = svg.getScreenCTM();
          var point = _point || svg.createSVGPoint();
          point.x = x;
          point.y = y;
          point = point.matrixTransform(matrix.inverse());
          return point || { x: 0, y: 0 };
        }

        /*
         * Transforms x data value to svg position. 
         */
        var unProjectX = plugin.unProjectX = function (value) {
          var bounds = axis_x.bounds || axis_x.range;
          var max = bounds.max;
          var min = bounds.min;
          var range = bounds.range || (max - min);
          return (axis_x.axisLength / range) * (value - min) + axis_x.chartRect.x1;
        }

        /*
         * Transforms y data value to svg position. 
         */
        var unProjectY = plugin.unProjectY = function(value) {
          var bounds = axis_y.bounds || axis_y.range;
          var max = bounds.max;
          var min = bounds.min;
          var range = bounds.range || (max - min);
          return axis_y.chartRect.y1 - (axis_y.axisLength / range) * (value - min);
        }

        /*
         * Transforms x svg position to x data value.. 
         */
        var project = plugin.project = function(value) {
          var bounds = axis_x.bounds || axis_x.range;
          var max = bounds.max;
          var min = bounds.min;
          var range = bounds.range || (max - min);
          return ((value - axis_x.chartRect.x1) * range / axis_x.axisLength) + min;
        }


      };
      return plugin;
    };
  }(window, document, Chartist));

  return Chartist.plugins.Tooltips_flex;

}));
