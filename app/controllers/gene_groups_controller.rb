class GeneGroupsController < ApplicationController
  def show
    @title = params[:name]
    @gene_group = GeneGroup.where(name: params[:name]).first
  end

  def names
    @names = GeneGroup.pluck(:name)
    respond_to do |format|
      format.json {render json:  @names.to_json}
    end
  end
end