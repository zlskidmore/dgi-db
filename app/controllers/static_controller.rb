class StaticController < ApplicationController
  before_filter :set_active

  caches_page :index, :getting_started, :faq, :downloads, :contact, :search_categories, :search_interactions, :search

  def search_categories
    @gene_categories   = DataModel::GeneClaimCategory.all_category_names
  end

  def search_interactions
    prepare_available_filter_actions
  end

  private
  @@help_pages = ["getting_started", "faq", "downloads", "contact"]
  def set_active
    @@help_pages.include?(params[:action]) ? instance_variable_set("@help_active", "active") : instance_variable_set("@#{params[:action]}_active", "active")
  end

  def prepare_available_filter_actions
    @sources           = DataModel::Source.source_names_with_interactions
    @gene_categories   = DataModel::GeneClaimCategory.all_category_names
    @interaction_types = DataModel::InteractionClaimType.all_type_names
  end
end
