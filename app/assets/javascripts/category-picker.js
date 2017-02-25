/*
  The following comments are parsed by Gulp include
  (https://www.npmjs.com/package/gulp-include) which uses
  Sprockets-style (https://github.com/sstephenson/sprockets)
  directives to concatenate multiple Javascript files into one.
*/
//= include _details.polyfill.js
//= include ../../../node_modules/govuk_frontend_toolkit/javascripts/govuk/stick-at-top-when-scrolling.js
//= include ../../../node_modules/govuk_frontend_toolkit/javascripts/govuk/stop-scrolling-at-footer.js

;(function(root) {

  "use strict";

  var GOVUK = root.GOVUK;

  // wrapper around the categories data
  var Categories = function (_categories) { 
    var primaries = []
    var self = this
    var parent

    this._containers = []
    this._categories = _categories
    this.save_last_state()
  }
  Categories.prototype.save_last_state = function () {
    this._lastState = $.extend(true, {}, this._categories)
  }
  Categories.prototype.tick_by_name = function (category_names) {
    var self = this

    this.save_last_state()
    $(this._categories).each(function () {
      var category = this
      var subcategories
      if ($.inArray(category.value, category_names) !== -1) {
        category.checked = !category.checked
        if (category.checked && category.parent) {
          self.get_parent_for(category).checked = true
        }
        // if category is a parent and is now not checked
        if ((!category.checked) && (category.parent === null)) {
          subcategories = $(self.get_children_for(category.value)).each(function () {
            var category = this
            if (category.checked) {
              self.tick_by_name([category.value])
            }
          })
        }
      }
    })
  }
  Categories.prototype.all = function () {
    return this._categories
  }
  Categories.prototype.get_primaries = function () {
    return $(this._categories).filter(function () {
      return this.parent === null
    })
  }
  Categories.prototype.get_children_for = function (value) {
    return $(this._categories).filter(function () {
      return this.parent === value
    })
  }
  Categories.prototype.get_parent_for = function (category) {
    var category_parent = category.parent

    return $(this.get_primaries()).filter(function () { return this.value === category_parent })[0]
  }
  Categories.prototype.get_filtered_names = function (filter) {
    return $(this._categories).filter(filter).map(function () { return this.value })
  }
  Categories.prototype.get_checked = function () {
    return $(this._categories).filter(function () { return this.checked })
  }
  Categories.prototype.diff = function (oldState, newState) {
    var diff = []

    oldState.each(function (idx) {
      var newCategory = newState[idx]
      if (this.checked !== newCategory.checked) {
        diff.push(newCategory)
      }
    })
    return diff
  }
  Categories.prototype.get_changes = function () {
    return this.diff(this._lastState, this._categories)
  }

  var categoryPicker = function () {
    var categories_data = $('#checkbox-tree input[type=checkbox]').map(function () {
      var $input = $(this)
      var $label = $input.parent()

      return {
        'value': $.trim($label.text()),
        'id': $input.attr('id'),
        'parent': null,
        'checked': $input.is(':checked')
      }
    })
    var globalCategories = new Categories(categories_data) 

    function setCounter () {
      var checked = globalCategories.get_checked().length
      var suffix = (checked === 1) ?  'category' : 'categories'

      $counter.text(checked + ' ' + suffix + ' selected.')
    }

    var $counter = $('#counter')
    var queryCache = ''
    function filterResults (query, dedupe) {
      var results = []
      var unique_results = []
      var i

      if (query) {
        results = globalCategories.get_filtered_names(function () {
          return (this.value.toLowerCase().indexOf(query.toLowerCase()) !== -1)
        })
        if (dedupe !== undefined) {
          // de-dupe results
          $(results).each(function () {
            var category_name = this
            if ($.inArray(category_name, unique_results) === -1) {
              unique_results.push(category_name)
            }
          })
          return unique_results;
        }
      }
      return results;
    }

    function renderCategories () {
      var updatedCategories = globalCategories.get_changes()

      $(updatedCategories).each(function () {
        var $input = $('#' + this.id)
        var action = (this.checked) ? 'addClass' : 'removeClass'

        $input.attr('checked', this.checked)
        $input.parent('label')[action]('selected')
      })
      setCounter()
    }

    renderCategories()
    setCounter()

    // make clicks on checkboxes update the categories state
    $('#checkbox-tree fieldset').on('click', function (evt) {
      var target = evt.target
      var targetNodeName = target.nodeName.toLowerCase()
      var categoryName

      function getLabelTextForInput (input) {
        var text = ''
        var siblings = $(input).parent().contents().each(function () {
          var childNode = this
          if (childNode.nodeType === 3) { // text node
            text += $(childNode).text()
          }
        })
        return $.trim(text)
      }

      function updateView (categoryName) {
        globalCategories.tick_by_name([categoryName])
        renderCategories()
        setCounter()
      }

      if (targetNodeName === 'input') {
        if (targetNodeName === 'input') {
          categoryName = getLabelTextForInput(target)
        } else {
          categoryName = $.trim($(target).text())
        }
        updateView(categoryName)
      }
    })
  }

  root.GOVUK.GDM.categoryPicker = categoryPicker
  categoryPicker()

  // Use GOV.UK sticky nav
  GOVUK.stickAtTopWhenScrolling.init()
  var $counter = $('#counter')
  GOVUK.stopScrollingAtFooter.addEl($counter, $counter.height())

})(window)
